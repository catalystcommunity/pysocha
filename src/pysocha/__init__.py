# -*- coding: utf-8 -*-
import sys

def hello() -> str:
    return "Hello from pysocha!"

def main():
    if len(sys.argv) > 1:
        print('Hello ' + sys.argv[1] + '!')
        return
    print('Hello World!')

