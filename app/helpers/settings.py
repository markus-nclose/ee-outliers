import configparser
from configparser import NoOptionError, NoSectionError

import logging
import argparse
import re

from helpers.singleton import singleton

PARSER = argparse.ArgumentParser()

SUBPARSERS = PARSER.add_subparsers(help="Run mode", dest="run_mode")
INTERACTIVE_PARSER = SUBPARSERS.add_parser('interactive')
DAEMON_PARSER = SUBPARSERS.add_parser('daemon')
TESTS_PARSER = SUBPARSERS.add_parser('tests')
PARSER_DIC = {'interactive': INTERACTIVE_PARSER,
              'daemon': DAEMON_PARSER,
              'tests': TESTS_PARSER}

HELP_CONFIG_MESSAGE = "Configuration file location"
HELP_USE_CASES_MESSAGE = "Additional use cases location"

# Interactive mode - options
INTERACTIVE_PARSER.add_argument("--config",
                                action='append',
                                help=HELP_CONFIG_MESSAGE,
                                required=True)

INTERACTIVE_PARSER.add_argument("--use-cases",
                                action='append',
                                help=HELP_USE_CASES_MESSAGE,
                                required=True)

# Daemon mode - options
DAEMON_PARSER.add_argument("--config",
                           action='append',
                           help=HELP_CONFIG_MESSAGE,
                           required=True)
DAEMON_PARSER.add_argument("--use-cases",
                           action='append',
                           help=HELP_USE_CASES_MESSAGE,
                           required=True)

# Tests mode - options
TESTS_PARSER.add_argument("--config",
                          action='append',
                          help=HELP_CONFIG_MESSAGE,
                          required=True)
TESTS_PARSER.add_argument("--use-cases",
                          action='append',
                          help=HELP_USE_CASES_MESSAGE,
                          required=True)


def print_failed_configs_and_exit(failed_config_paths):
    """
    Method to check if failed_config_paths contains some file path that failed to load.
    If true, it throws an error message with the command-line usage corresponding to current_parser and the list of
    the failed config paths.

    :param failed_config_paths: Set of string
    """
    if failed_config_paths:
        err_msg = "Failed to load %d configuration file(s):\n" % len(failed_config_paths)
        for failed_config_path in failed_config_paths:
            err_msg += "\t - %s\n" % failed_config_path

        # logs error message to console and exit
        logging.error(err_msg)
        exit(2)


def extract_whitelist_literal_from_value(value):
    """
    Converts a whitelist element from the configuration file into a set of unique elements to check.
    Example: this converts "a, b, c, d  ,e" into [a, b, c, d, e]. Values are stripped for the case where users
    include a "space" at the end of a whitelist value which could result in incorrect matching.
    :param value: the whitelist string
    :return: the array of whitelist elements
    """
    list_whitelist_element = set()
    for one_whitelist_config_file_value in value.split(','):
        list_whitelist_element.add(one_whitelist_config_file_value.strip())
    return list_whitelist_element


def extract_whitelist_regex_from_value(value):
    """
    Converts a whitelist element from the configuration file into a set of unique elements to check.
    Values are first checked to see if they are valid regular expressions.
    Example: this converts "^.*apples$,^apples.*$ into a set of 2 valid regular expresion objects.
    Values are stripped for the case where users include a "space" at the end of a whitelist value which could
    result in incorrect matching.
    :param value: the whitelist string
    :return: the tuple of correctly parsed & incorrectly parsed regular expressions
    """
    list_compile_regex_whitelist_value = set()
    failing_regular_expressions = set()
    for whitelist_val_to_check in value.split(","):
        try:
            list_compile_regex_whitelist_value.add(re.compile(whitelist_val_to_check.strip(), re.IGNORECASE))
        except Exception:
            # something went wrong compiling the regular expression, probably because of a user error such as
            # unbalanced escape characters. We should just ignore the regular expression and continue (and let
            # the user know in the beginning that some could not be compiled).  Even if we check for errors
            # in the beginning of running outliers, we might still run into issues when the configuration
            # changes during running of ee-outlies. So this should catch any remaining errors in the
            # whitelist that could occur with regular expressions.
            failing_regular_expressions.add(whitelist_val_to_check)

    return list_compile_regex_whitelist_value, failing_regular_expressions


def extract_whitelist_regex_from_settings_section(whitelist_regexps_config_items):
    list_whitelist_regexps = list()
    failing_regular_expressions = set()

    # Verify that all regular expressions in the whitelist are valid.
    # If this is not the case, log an error to the user, as these will be ignored.
    for each_whitelist_configuration_file_value in whitelist_regexps_config_items:
        new_compile_regex_whitelist_value, value_failing_regular_expressions = \
            extract_whitelist_regex_from_value(each_whitelist_configuration_file_value)

        # Fixes bug #462
        if len(new_compile_regex_whitelist_value) > 0:
            list_whitelist_regexps.append(new_compile_regex_whitelist_value)

        if len(value_failing_regular_expressions) > 0:
            failing_regular_expressions.union(value_failing_regular_expressions)

    return list_whitelist_regexps, failing_regular_expressions


def extract_whitelist_literals_from_settings_section(fetch_whitelist_literals_elements):
    list_whitelist_literals = list()

    for each_whitelist_configuration_file_value in fetch_whitelist_literals_elements:
        list_whitelist_literals.append(extract_whitelist_literal_from_value(str(
            each_whitelist_configuration_file_value)))
    return list_whitelist_literals


@singleton
class Settings:
    """
    Class to keep track of all configured settings.
    Includes loading & parsing the configuration file(s) provided as command line arguments.
    """
    def __init__(self):
        self.args = None
        self.config = None

        self.loaded_config_paths = None
        self.failed_config_paths = None

        self.whitelist_literals_config = None
        self.whitelist_regexps_config = None
        self.failing_regular_expressions = set()

        self.args = PARSER.parse_args()
        self.parser_dic = PARSER_DIC

        self.process_configuration_files()

    def process_configuration_files(self):
        """
        Parse configuration and save some value
        """
        config_paths = self.args.config

        # Read configuration files
        config = configparser.RawConfigParser(interpolation=None, strict=False)
        config.optionxform = str  # preserve case sensitivity in config keys, important for derived field names

        self.loaded_config_paths = config.read(config_paths)
        self.failed_config_paths = set(config_paths) - set(self.loaded_config_paths)

        if self.failed_config_paths:
            print_failed_configs_and_exit(self.failed_config_paths)

        # At this point we know all configuration files can be loaded - let's parse them!
        self.config = config

        try:
            fetch_whitelist_literals_elements = list(dict(self.config.items("whitelist_literals")).values())
        except NoSectionError:
            fetch_whitelist_literals_elements = list()

        try:
            whitelist_regexps_config_items = dict(self.config.items("whitelist_regexps")).values()
        except NoSectionError:
            whitelist_regexps_config_items = list()

        # Literal whitelist
        self.whitelist_literals_config = \
            extract_whitelist_literals_from_settings_section(fetch_whitelist_literals_elements)
        # Regex whitelist
        self.whitelist_regexps_config, self.failing_regular_expressions = \
            extract_whitelist_regex_from_settings_section(whitelist_regexps_config_items)

        try:
            self.print_outliers_to_console = self.config.getboolean("general", "print_outliers_to_console")
        except NoOptionError:
            self.print_outliers_to_console = 0

        # Could produce an error, but don't catch it. Crash program if not define
        self.es_save_results = self.config.getboolean("general", "es_save_results")

        try:
            self.list_derived_fields = self.config.items("derivedfields")
        except NoSectionError:
            self.list_derived_fields = dict()

        try:
            self.list_assets = self.config.items("assets")
        except NoSectionError:
            self.list_assets = dict()

    def check_no_duplicate_key(self):
        """
        Method to check if some duplicates are present in the configuration

        :return: the error (that contain message with duplicate), None if no duplicate
        """
        try:
            config = configparser.RawConfigParser(interpolation=None, strict=True)
            config.optionxform = str  # preserve case sensitivity in config keys, important for derived field names
            config.read(self.args.config)
        except (configparser.DuplicateOptionError, configparser.DuplicateSectionError) as err:
            return err
        return None
