# -*- coding: utf-8 -*-
import typer
from typing_extensions import Annotated

app = typer.Typer()

@app.command()
def hello(name: Annotated[str, typer.Argument()] = 'World') -> str:
    return "Hello {name}!"

@app.command()
def preview(config_file: Annotated[typer.FileText, typer.Option()] = './config.yaml'):
    for line in config_file:
        print(f"config line: {line}", end='')

@app.command()
def build(config_file: Annotated[typer.FileText, typer.Option()] = './config.yaml'):
    for line in config_file:
        print(f"config line: {line}", end='')

