# CGT Cell Analysis Demo

A demo project for microscopy-based cell analysis in CGT workflows.

This repository presents an end-to-end experimental pipeline that includes:
- image stitching for tiled microscopy images
- well matching between optical and PCR-related indexing logic
- segmentation-assisted preprocessing
- cell count prediction model training and inference

## Why this project
In cell and gene therapy workflows, image-based analysis often requires multiple preprocessing and modeling steps before meaningful cell-level metrics can be obtained.  
This project demonstrates how those steps can be connected into a reproducible engineering pipeline.

## Pipeline Overview
1. Stitch tiled images into a unified view
2. Match well positions across acquisition contexts
3. Prepare training labels and preprocess data
4. Train a cell-count prediction model
5. Run inference on new samples

## Repository Structure
- `src/stitching`: image stitching modules
- `src/well_matching`: well indexing and matching logic
- `src/segmentation`: cell segmentation-related experiments
- `src/training`: preprocessing, label generation, model training
- `src/inference`: prediction pipeline

## Demo
[Add GIF / screenshots here]

## Tech Stack
Python, OpenCV, NumPy, model training pipeline, experiment scripts

## What I focused on
- designing a multi-step analysis pipeline
- organizing preprocessing and training logic
- building reusable experimental modules
- validating intermediate outputs for microscopy-based analysis

## Note
This repository is a demo-oriented reconstruction for portfolio purposes and does not include any proprietary datasets or confidential production code.
