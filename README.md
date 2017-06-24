# pycambot
## Overview
The goal of `pycambot` is to replace a human camera operator with an autonomous pan-tilt-zoom camera.  The application it was designed for is live streaming of a human speaker, with the speaker moving against a static background, and no other subjects in motion. 

The bot uses OpenCV native face detection to identify the subject. It will revert to a safe PTZ position if it loses the subject's face for a few seconds.

The only camera tested with `pycambot` so far is the PTZOptics 20xUSB. The solution was tested on a UDOO x86 SOC board, an Intel all-in-one board with the processing power to capture HD video via a USB 3.0 interface and run it through OpenCV and dlib libraries at a reasonable frame rate.

## Setup
If are new to OpenCV, save yourself some time and use Docker images for kickstarting your environment. I recommend running Docker on Ubuntu and using [one of these images](https://hub.docker.com/r/victorhcm/opencv/). But first read the [excellent tutorial](http://www.pyimagesearch.com/2016/10/24/ubuntu-16-04-how-to-install-opencv/) from whose steps the Docker image was constructed.

## Solution elements:
+ Python 2.7
+ OpenCV 3.2
+ HD PTZ camera supporting VISCA over TCP and USB 3.0 HD video transfer
