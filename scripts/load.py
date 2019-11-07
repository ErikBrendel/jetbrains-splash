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


INDEX = "https://data.services.jetbrains.com/products?code=IIU&release.type=release"


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


def extract_image(version_and_path: (version.Version, str)) -> str:
    name = str(version_and_path[0])
    image_base_path = '../images/' + name
    if os.path.isdir(image_base_path):
        print("Skipping existing " + name)
        return image_base_path
    print("Working on " + name)
    t = tarfile.open(version_and_path[1], "r:gz")
    content_dir = os.path.commonprefix(t.getnames())
    resources_name = content_dir + "lib/resources.jar"
    resources_base_path = '../download/resources'
    t.extract(resources_name, resources_base_path)
    resources_zip = zipfile.ZipFile(resources_base_path + "/" + resources_name)
    resources_zip.extract("idea_logo.png", image_base_path)
    try:
        resources_zip.extract("idea_logo@2x.png", image_base_path)
    except KeyError:
        print("Skipping high res image for " + name + ", seems not to exist")
    return image_base_path


def generate_result(images: List[Tuple[version.Version, str]]):
    with open("../index.html", "w") as f:
        f.write("<html><head><title>IDEA Splash screens</title></head><body>")
        for image in images:
            name = str(image[0])
            f.write("<h3>" + name + "</h3>")
            f.write("<a href=images/" + name + "/idea_logo@2x.png><img src=images/" + name + "/idea_logo.png/></a>")
        f.write("</body></html>")


def print_marker(text: str):
    print("\n========== " + text + "\n")


if __name__ == "__main__":
    print_marker("fetching latest release information")
    index_json = requests.get(INDEX).json()
    downloads = get_major_download_links(index_json[0]['releases'])

    print_marker("downloading releases")
    local_releases = [(download[0], download_file(download[1])) for download in downloads.values()]

    print_marker("extracting images")
    images = [(release[0], extract_image(release)) for release in local_releases]

    print_marker("Generating result")
    generate_result(images)

    print_marker("All Done!")
