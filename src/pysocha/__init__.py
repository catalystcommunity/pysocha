# -*- coding: utf-8 -*-
import os
import typer
import yaml
from yaml import Loader
from typing_extensions import Annotated
from .config import override_config
from .preview import makePreviewServer
from .build import buildSite

app = typer.Typer()


def main():
    app()


def initialize(config_file: str):
    return override_config(yaml.load(config_file, Loader=Loader))

@app.command()
def hello(name: Annotated[str, typer.Argument()] = 'World') -> str:
    print(f"Hello {name}!")

@app.command()
def preview(
    config_file: Annotated[typer.FileText, typer.Option('--config-file', '-c')] = './config.yaml',
    verbose: Annotated[bool, typer.Option('--verbose', '-v')] = False,
):
    config = initialize(config_file)
    output_dir = os.path.join(os.getcwd(), config['outputDir'])
    server = makePreviewServer(output_dir, config['startPage'], config['defaultExtension'])
    server.config['SEND_FILE_MAX_AGE_DEFAULT'] = 5
    buildSite(config, verbose=verbose)
    server.run(host='0.0.0.0')


@app.command()
def build(
    config_file: Annotated[typer.FileText, typer.Option('--config-file', '-c')] = './config.yaml',
    verbose: Annotated[bool, typer.Option('--verbose', '-v')] = False,
):
    config = initialize(config_file)
    buildSite(config, verbose=verbose)
