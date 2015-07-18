#!/usr/bin/env python
# Copyright (C) 2015 Dmitry Rodionov
# This software may be modified and distributed under the terms
# of the MIT license. See the LICENSE file for details.

import logging
from shutil import move
from os import path, environ
from random import SystemRandom
from string import ascii_letters
from subprocess import check_output
from zipfile import ZipFile, BadZipfile
from lib.core.packages import Package, choose_package_class

log = logging.getLogger(__name__)

class Zip(Package):

    real_package = None

    def prepare(self):
        password = self.options.get("password")
        files = self._extract(self.target, password)
        if not files or len(files) == 0:
            raise Exception("Invalid (or empty) zip archive: %s" % self.target)
        # Look for a file to analyse
        target_name = self.options.get("file")
        if not target_name:
            # If no file name is provided via option, take the first file
            target_name = files[0]
            log.debug("Missing file option, auto executing: %s", target_name)

        filepath = path.join(environ.get("TEMP", "/tmp"), target_name)
        # Remove the trailing slash (if any)
        if filepath.endswith("/"):
            self.target = filepath[:-1]
        else:
            self.target = filepath

        # Since we don't know what kind of file we're going to analyse, let's
        # detect it automatically and create an appropriate analysis package
        # for this file
        file_info = _fileinfo(self.target)
        pkg_class = choose_package_class(file_info, target_name)

        if not pkg_class:
            raise Exception("Unable to detect analysis package for the file %s" % target_name)
        else:
            log.debug("Analysing file \"%s\" using package \"%s\"", target_name, pkg_class.__name__)

        kwargs = {
            "options" : self.options,
            "timeout" : self.timeout
        }
        # We'll forward start() method invocation to the proper package later
        self.real_package = pkg_class(self.target, self.host, **kwargs)

    def start(self):
        # We have nothing to do here; let the proper package do it's job
        self.prepare()
        if not self.real_package:
            raise Exception("Invalid analysis package, aborting")
        self.real_package.start()

    def _extract(self, archive_path, password):
        # Verify that the archive is actually readable
        if _verify_archive(archive_path) == False:
            return None
        # Test if zip file contains a file named as itself.
        if _is_overwritten(archive_path):
            log.debug("ZIP file contains a file with the same name, original is \
            going to be overwrite")
            new_zip_path = archive_path + _random_extension()
            move(archive_path, new_zip_path)
            archive_path = new_zip_path
        # Extraction.
        extract_path = environ.get("TEMP", "/tmp")
        with ZipFile(archive_path, "r") as archive:
            try:
                archive.extractall(path=extract_path, pwd=password)
            except BadZipfile:
                raise Exception("Invalid Zip file")
            # Try to extract it again, but with a default password
            except RuntimeError:
                try:
                    archive.extractall(path=extract_path, pwd="infected")
                except RuntimeError as err:
                    raise Exception("Unable to extract Zip file: %s" % err)
            finally:
                self._extract_nested_archives(archive, extract_path, password)
        return archive.namelist()

    def _extract_nested_archives(self, archive, where, password):
        for name in archive.namelist():
            if name.endswith(".zip"):
                self._extract(path.join(where, name), password)


def _is_overwritten(zip_path):
    with ZipFile(zip_path, "r") as archive:
        try:
            # Test if zip file contains a file named as itself
            for name in archive.namelist():
                if name == path.basename(zip_path):
                    return True
            return False
        except BadZipfile:
            raise Exception("Invalid Zip file")

def _random_extension(length=5):
    return '.' + ''.join(SystemRandom().choice(ascii_letters) for _ in range(length))


def _fileinfo(target):
    raw = check_output(["file", target])
    return raw[raw.index(":")+2:]


def _verify_archive(archive_path):
    try:
        with ZipFile(archive_path, "r") as archive:
            archive.close()
            return True
    except BadZipfile:
        return False
