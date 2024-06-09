# -*- coding: utf-8 -*-
import typer
import yaml
from pprint import pprint
from typing_extensions import Annotated
from .config import override_config
from .markdown import parseCommonMark

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
    return override_config(yaml.load(config_file))

@app.command()
def hello(name: Annotated[str, typer.Argument()] = 'World') -> str:
    return "Hello {name}!"

@app.command()
def preview(config_file: Annotated[typer.FileText, typer.Option()] = './config.yaml'):
    print(override_config(config_file))

@app.command()
def build(config_file: Annotated[typer.FileText, typer.Option()] = './config.yaml'):
    pprint(override_config(config_file))
    pprint(parseCommonMark(mark))

