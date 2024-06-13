# -*- coding: utf-8 -*-
import os
import typer
import yaml
from yaml import Loader
from pprint import pprint
from typing_extensions import Annotated
from .config import override_config
from .markdown import parseCommonMark
from .preview import makePreviewServer
from .build import buildSite

mark = """---
Title: Foo and Bar
Author: Me and myself
Date: 2004-09-25:12:28:00
---
### This is a header

* List 1
* List 2
* List 3 

This is some stuff *bold* or not.
"""

app = typer.Typer()

def initialize(config_file: str):
    return override_config(yaml.load(config_file, Loader=Loader))

@app.command()
def hello(name: Annotated[str, typer.Argument()] = 'World') -> str:
    print(f"Hello {name}!")

@app.command()
def preview(config_file: Annotated[typer.FileText, typer.Option('--config-file', '-c')] = './config.yaml'):
    config = initialize(config_file)
    output_dir = os.path.join(os.getcwd(), config['outputDir'])
    server = makePreviewServer(output_dir, config['startPage'], config['defaultExtension'])
    server.config['SEND_FILE_MAX_AGE_DEFAULT'] = 5
    buildSite(config)
    server.run(host='0.0.0.0')


@app.command()
def build(config_file: Annotated[typer.FileText, typer.Option('--config-file', '-c')] = './config.yaml'):
    config = initialize(config_file)
    pprint(config)
    pprint(parseCommonMark(mark)['markdown'])
    buildSite(config)

