import os
from kaggle.api.kaggle_api_extended import KaggleApi

# Initialize API
api = KaggleApi()
api.authenticate()

# Download dataset
print("Downloading Fall Detection Dataset...")
api.dataset_download_files(
    'uttejkumarkandagatla/fall-detection-dataset',
    path='data',
    unzip=True
)
print("Download complete!")