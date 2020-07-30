#!/usr/bin/env python3

from urllib.parse import urlparse
import os
import shutil
import sys
from typing import *

import requests
import tarfile
import zipfile
from packaging import version

#  the splash images for IDE [0] are found at:
#  "*.tar.gz!/<root>/lib/[1].jar!/[2].png"
#  "*.tar.gz!/<root>/lib/[1].jar!/[2]@2x.png"
#  <VERSION> will be replaced by eg 20192
IDE = [
    ('IIU', 'resources', 'idea_logo'),
    ('WS', 'webstorm', 'artwork/webide_logo'),
    ('PS', 'phpstorm', 'artwork/webide_logo'),
    ('PCP', 'pycharm', 'pycharm_logo'),
    ('CL', 'clion', 'artwork/clion_splash'),
    ('RD', 'rider', 'rider/artwork/Rider_<VERSION>_splash'),
    ('RM', 'rubymine', 'artwork/rubymine_logo'),
]

ALTERNATIVE_LOGO_POSITIONS = [
    'rider/artwork/Rider_<VERSIONDOT>_splash',
    'rider/artwork/StaticSplash',
    'rider/artwork/Rider_splash',
]

ALTERNATIVE_RESOURCE_JARS = [
    'branding',
    'resources_en',
]

IDE_NAMES = [ide[0] for ide in IDE]
IDE_NAMES_STR = ",".join(IDE_NAMES)
INDEX = "https://data.services.jetbrains.com/products?code=" + IDE_NAMES_STR + "&release.type=release"


def download_with_progress(url: str, file_name: str):
    with open(file_name, "wb") as f:
        response = requests.get(url, stream=True)
        total_length = response.headers.get('content-length')

        if total_length is None:  # no content length header
            f.write(response.content)
        else:
            dl = 0
            total_length = int(total_length)
            for data in response.iter_content(chunk_size=4096):
                dl += len(data)
                f.write(data)
                done = int(50 * dl / total_length)
                sys.stdout.write("\r[%s%s]" % ('=' * done, ' ' * (50 - done)))
                sys.stdout.flush()
            print()


def get_major_download_links(releases: List) -> Dict[version.Version, Tuple[version.Version, str]]:
    data: Dict[version.Version, Tuple[version.Version, str]] = {}  # majorVer -> (minorVer, url)

    for release in releases:
        minor_version = version.parse(release['version'])
        major_version = version.parse(release['majorVersion'])
        existing_major = data.get(major_version)
        if existing_major is not None and existing_major[0] > minor_version:
            # print("ignoring " + str(minor_version) + " in favor of " + str(existing_major[0]))
            continue

        # the linux one is provided as archive (.tar.gz), also in old versions
        dl: str = release.get('downloads', {}).get('linux', {}).get('link')
        if dl is None:
            # print("ignoring " + str(minor_version) + " because it has no download!")
            continue

        data[major_version] = (minor_version, dl)
    return data


def download_file(url: str) -> str:
    name = os.path.basename(urlparse(url).path)
    local_file = '../download/' + name
    if os.path.isfile(local_file):
        # print("Skipping existing " + name)
        return local_file
    print("Now downloading " + name + "...")
    download_with_progress(url, local_file)
    r = requests.get(url)
    with open(local_file, 'wb') as f:
        f.write(r.content)
    return local_file


def extract_image(version_and_path: (version.Version, str), ide_name: str, default_jar_name: str, default_path: str) -> str:
    name = str(version_and_path[0])
    image_base_path = '../images/' + ide_name + "/" + name

    if os.path.isdir(image_base_path):
        # print("Skipping existing " + name)
        return image_base_path
    print("Working on " + name)

    try:
        t = tarfile.open(version_and_path[1], "r:gz")
        content_dir = os.path.commonprefix(t.getnames())
        if not content_dir.endswith("/"):
            content_dir += "/"
        jar_names = [default_jar_name] + ALTERNATIVE_RESOURCE_JARS
        for jar_name in jar_names:
            try:
                resources_name = content_dir + "lib/" + jar_name + ".jar"
                resources_base_path = '../download/resources'
                t.extract(resources_name, resources_base_path)
                with zipfile.ZipFile(resources_base_path + "/" + resources_name) as resources_zip:
                    for logo_path in logo_path_options(default_path, version_and_path[0]):
                        if extract_to(resources_zip, logo_path + ".png", image_base_path, "logo.png"):
                            extract_to(resources_zip, logo_path + "@2x.png", image_base_path, "logo@2x.png")
                            return image_base_path
            except KeyError:
                pass  # try next
        print("Failed! There seems to be no image for that!")
        return image_base_path
    except KeyError:
        print("Failed! Error! There seems to be no image for that!")
    return image_base_path


def logo_path_options(default_path: str, version: version.Version) -> List[str]:
    all_paths = [default_path] + ALTERNATIVE_LOGO_POSITIONS
    return [p.replace("<VERSION>", str(version).replace(".", "")).replace("<VERSIONDOT>", str(version)) for p in
            all_paths]


def extract_to(z: zipfile, zip_file: str, out_dir: str, out_file: str) -> bool:
    try:
        with z.open(zip_file) as zf:
            if not os.path.isdir(out_dir):
                os.makedirs(out_dir)
            with open(out_dir + "/" + out_file, 'wb') as f:
                shutil.copyfileobj(zf, f)
        return True
    except KeyError:
        return False


def generate_result(image_data: Dict[str, List[Tuple[version.Version, str]]]):
    version_data: Dict[version.Version, Dict[str, str]] = {}  # verison -> (ide->img)
    old_versions: Dict[str, List[str]] = {}  # ide -> images
    old_version_count = 0
    for ide_name in IDE_NAMES:
        old_versions[ide_name] = []
        for img_data in image_data.get(ide_name, []):
            v = img_data[0]
            path = img_data[1]
            if float(str(v)) < 2010:
                old_versions[ide_name].append(path)
                old_version_count = max(old_version_count, len(old_versions[ide_name]))
            else:
                if v not in version_data:
                    version_data[v] = {}
                version_data[v][ide_name] = path
    with open("../index.html", "w") as f:
        f.write("<html><head><title>JetBrains IDE Splash screens</title></head><body>")
        f.write("<table>")
        for version, ide_paths in reversed(sorted(version_data.items())):
            f.write("<tr>")
            f.write("<td>" + str(version) + "</td>")
            for ide_name in IDE_NAMES:
                path = ide_paths.get(ide_name, 'not_existing')
                f.write("<td>")
                f.write("<a href=images/" + path + "/logo@2x.png><img src=images/" + path + "/logo.png/></a>")
                f.write("</td>")
            f.write("</tr>")
        for i in range(old_version_count):
            f.write("<tr>")
            f.write("<td>" + "" + "</td>")
            for ide_name in IDE_NAMES:
                path = old_versions[ide_name][i] if i < len(old_versions[ide_name]) else "not_existing"
                f.write("<td>")
                f.write("<a href=images/" + path + "/logo@2x.png><img src=images/" + path + "/logo.png/></a>")
                f.write("</td>")
            f.write("</tr>")

        f.write("</table>")
        f.write("</body></html>")


def print_marker(text: str):
    print("\n========== " + text + "\n")


if __name__ == "__main__":
    print_marker("fetching latest release information")
    index_json = requests.get(INDEX).json()

    image_data = {}
    for ide_info, ide_json in zip(IDE, index_json):
        ide_name = ide_info[0]
        print_marker("parsing info for " + ide_name)
        downloads = get_major_download_links(ide_json['releases'])

        print_marker("downloading releases for " + ide_name)
        local_releases = [(version, download_file(download[1])) for (version, download) in downloads.items()]

        print_marker("extracting images for " + ide_name)
        images = [(release[0], extract_image(release, ide_name, ide_info[1], ide_info[2])) for release in
                  local_releases]

        image_data[ide_name] = images

    print_marker("Generating result")
    generate_result(image_data)

    print_marker("All Done!")
