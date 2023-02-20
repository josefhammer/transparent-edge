#!/usr/bin/env python3
"""
Downloads an image and generates a message body for a TensorFlow Serving POST message body.
"""

import base64
import requests
import argparse


def downloadImage(imageUrl):
    """
    Downloads the image at imageUrl and returns the content.
    """
    req = requests.get(imageUrl, stream=True)
    req.raise_for_status()
    return req.content


def createMsgBody(imageBytes):
    """
    Returns the predict request body with the image in base64.
    """
    imgB64 = base64.b64encode(imageBytes).decode('utf-8')
    return f'{{"instances":[{{"b64":"{ imgB64 }"}}]}}'


def writeFile(filename, content):
    """
    Writes content to file.
    """
    with open(filename, "w") as f:
        f.write(content)


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('outputFile')
    parser.add_argument('imageUrl', help="E.g.: https://tensorflow.org/images/blogs/serving/cat.jpg")
    args = parser.parse_args()

    writeFile(args.outputFile, createMsgBody(downloadImage(args.imageUrl)))
