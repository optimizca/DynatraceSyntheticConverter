import os
import re

from click import command

import glob
import json
from pathlib import Path
import logging


@command(
    name='generate',
    help='''
    Generate python scripts from Dynatrace synthetic monitor JSON.
    Generated scripts are placed in the output directory and will overwrite existing scripts of the same name.  
    ''')
def generate():
    logging.info(f'-----Launching generate step-----')

    if not os.path.exists('output'):
        os.makedirs('output')

    for file in glob.iglob('input/*.json'):
        filename = Path(file).stem
        schema = json.loads(open(file).read())
        if schema['type'] == 'clickpath':
            logging.info(f'Converting {filename}')

            events = schema['events']
            code = open('DynatraceSyntheticConverter/resources/conversionSnippets/base.txt').read()
            eventsCode = ''

            hasUnsupportedElements = False
            for event in events:
                if event['type'] == 'navigate':
                    eventsCode += __genNavigateCode(event)
                elif event['type'] == 'keystrokes':
                    eventsCode += __genKeystrokesCode(event)
                elif event['type'] == 'click':
                    eventsCode += __genClickCode(event)
                elif event['type'] == 'javascript':
                    eventsCode += __genJsCode(event)
                elif event['type'] == 'selectOption':
                    eventsCode += __genSelectOptionCode(event)
                else:
                    hasUnsupportedElements = True
                    logging.debug(f'{event["type"]} is not yet supported')
                if 'validate' in event:
                    eventsCode += __genTextMatchCode(event)

            if hasUnsupportedElements:
                logging.info(f'{filename} not fully converted, contains unsupported elements')

            code = code.replace('# $EVENT_STEPS', eventsCode)

            with open(f'output/{Path(file).stem}.py', 'w') as outfile:
                logging.debug(f'Saving {filename}')
                outfile.write(code)
        else:
            logging.error(f'Schema type {schema["type"]} for {filename} is not supported. Skipping...')


def __genNavigateCode(event) -> str:
    url = event['url']
    description = event['description']
    code = open('DynatraceSyntheticConverter/resources/conversionSnippets/navigate.txt').read() \
        .replace('$URL', url) \
        .replace('$DESCRIPTION', description)
    return code


def __genKeystrokesCode(event):
    # next event target locator where the type is css and value contains a #, else grab the first one
    locators = event['target']['locators']
    selector = __selectorFromLocators(locators)
    keys = event['textValue']
    description = event['description']
    code = open('DynatraceSyntheticConverter/resources/conversionSnippets/keystrokes.txt').read() \
        .replace('$SELECTOR_TYPE', selector['selectorType']) \
        .replace('$SELECTOR_STRING', selector['selectorString']) \
        .replace('$SELECTOR_CODE', selector['selectorCode']) \
        .replace('$KEYS', keys) \
        .replace('$DESCRIPTION', description)
    return code


def __genClickCode(event):
    locators = event['target']['locators']
    selector = __selectorFromLocators(locators)
    description = event['description']
    code = open('DynatraceSyntheticConverter/resources/conversionSnippets/click.txt').read() \
        .replace('$SELECTOR_TYPE', selector['selectorType']) \
        .replace('$SELECTOR_STRING', selector['selectorString']) \
        .replace('$SELECTOR_CODE', selector['selectorCode']) \
        .replace('$DESCRIPTION', description)
    return code


def __genSelectOptionCode(event):
    locators = event['target']['locators']
    selector = __selectorFromLocators(locators)
    description = event['description']
    selections = event['selections'][0]['index']  # TODO: this'll not work for multi selects
    code = open('DynatraceSyntheticConverter/resources/conversionSnippets/selectOption.txt').read() \
        .replace('$SELECTOR_TYPE', selector['selectorType']) \
        .replace('$SELECTOR_STRING', selector['selectorString']) \
        .replace('$SELECTOR_CODE', selector['selectorCode']) \
        .replace('$DESCRIPTION', description) \
        .replace('$INDEX', str(selections))
    return code


def __genTextMatchCode(event):
    code = ""
    for validator in event['validate']:
        if validator['type'] == 'content_match' or validator['type'] == 'text_match':
            if validator['failIfFound']:
                code += open('DynatraceSyntheticConverter/resources/conversionSnippets/textMatchFailIfFound.txt').read()
            else:
                code += open(
                    'DynatraceSyntheticConverter/resources/conversionSnippets/textMatchFailIfNotFound.txt').read()
            code = code.replace('$TEXT', validator['match'])
        if validator['type'] == 'element_match':
            locators = validator['target']['locators']
            selector = __selectorFromLocators(locators)
            if validator['failIfFound']:
                code += open(
                    'DynatraceSyntheticConverter/resources/conversionSnippets/elementMatchFailIfFound.txt').read()
            else:
                code += open(
                    'DynatraceSyntheticConverter/resources/conversionSnippets/elementMatchFailIfNotFound.txt').read()
            code = code.replace('$SELECTOR_TYPE',  selector['selectorType']) \
                .replace('$SELECTOR_STRING', selector['selectorString']) \
                .replace('$SELECTOR_CODE', selector['selectorCode'])
    return code


def __selectorFromLocators(locators):
    cssIdLocator = \
        next((locator for locator in locators if locator['type'] == 'css' and 'contains' not in locator['value']), None)
    if cssIdLocator is not None:
        cssID = cssIdLocator['value'].replace("\"", "\\\"")
        return {
            'selectorType': 'By.CSS_SELECTOR',
            'selectorString': cssID,
            'selectorCode': f'driver.find_element_by_css_selector("{cssID}")'
        }

    cssContainsLocator = \
        next((locator for locator in locators if locator['type'] == 'css' and 'contains' in locator['value']), None)
    if cssContainsLocator is not None:
        val = cssContainsLocator['value']
        content = re.search(r'\((.*)\)', val).group(1).replace("\"", "\\\"")
        tag = val.split(':')[0]
        return {
            'selectorType': 'By.XPATH',
            'selectorString': f"//{tag}[contains(text(), {content})]",
            'selectorCode': f'driver.find_element_by_xpath("//{tag}[contains(text(), {content})]")'
        }

    cssDomNameLocator = \
        next((locator for locator in locators if locator['type'] == 'dom' and 'getElementsByName' in locator['value']),
             None)
    if cssDomNameLocator is not None:
        val = cssDomNameLocator['value']
        content = re.search(r'\((.*)\)', val).group(1)

        return {
            'selectorType': 'By.NAME',
            'selectorString': content,
            'selectorCode': f'driver.find_element_by_name({content})'
        }

    return 'None  # TODO: locator found is ' + locators[0]["value"].replace("\"", "\\\"")


def __genJsCode(event):
    description = event['description']
    code = open('DynatraceSyntheticConverter/resources/conversionSnippets/jsCode.txt').read() \
        .replace('$DESCRIPTION', description) \
        .replace('$JS_CODE', event['javaScript'].replace('\n', '\t\t'))
    return code
