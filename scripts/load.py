#!/usr/bin/env python3.7

from urllib.parse import urlparse
import os
import sys
from typing import *

import requests
import requests_cache
import tarfile
import zipfile
from packaging import version

requests_cache.install_cache()


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
            print("ignoring " + str(minor_version) + " in favor of " + str(existing_major[0]))
            continue

        # the linux one is provided as archive (.tar.gz), also in old versions
        dl: str = release.get('downloads', {}).get('linux', {}).get('link')
        if dl is None:
            print("ignoring " + str(minor_version) + " because it has no download!")
            continue

        data[major_version] = (minor_version, dl)
    return data


def download_file(url: str) -> str:
    name = os.path.basename(urlparse(url).path)
    local_file = '../download/' + name
    if os.path.isfile(local_file):
        print("Skipping existing " + name)
        return local_file
    print("Now downloading " + name + "...")
    download_with_progress(url, local_file)
    r = requests.get(url)
    with open(local_file, 'wb') as f:
        f.write(r.content)
    return local_file


def extract_image(version_and_path: (version.Version, str), ide_name: str, jar_name: str, logo_path: str) -> str:
    name = str(version_and_path[0])
    logo_path = logo_path.replace("<VERSION>", str(version_and_path[0]).replace(".", ""))
    image_base_path = '../images/' + ide_name + "/" + name
    result_path = image_base_path + "/" + logo_path
    if os.path.isdir(image_base_path):
        print("Skipping existing " + name)
        return result_path
    print("Working on " + name)
    try:
        t = tarfile.open(version_and_path[1], "r:gz")
        content_dir = os.path.commonprefix(t.getnames())
        resources_name = content_dir + "lib/" + jar_name + ".jar"
        resources_base_path = '../download/resources'
        t.extract(resources_name, resources_base_path)
        resources_zip = zipfile.ZipFile(resources_base_path + "/" + resources_name)
        resources_zip.extract(logo_path + ".png", image_base_path)
        try:
            resources_zip.extract(logo_path + "@2x.png", image_base_path)
        except KeyError:
            print("Skipping high res image for " + name + ", seems not to exist")
    except KeyError:
        print("Failed! There seems to be no image for that!")
        pass
    return result_path


def generate_result(image_data: Dict[str, List[Tuple[version.Version, str]]]):
    version_data: Dict[version.Version, Dict[str, str]] = {}  # verison -> (ide->img)
    for ide_name in IDE_NAMES:
        for img_data in image_data.get(ide_name, []):
            v = img_data[0]
            path = img_data[1]
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
                f.write("<a href=images/" + path + "@2x.png><img src=images/" + path + ".png/></a>")
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
        images = [(release[0], extract_image(release, ide_name, ide_info[1], ide_info[2])) for release in local_releases]

        image_data[ide_name] = images

    print_marker("Generating result")
    generate_result(image_data)

    print_marker("All Done!")
