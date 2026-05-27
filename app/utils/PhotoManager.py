import os
import logging
from collections import defaultdict

from bson import ObjectId
from bson.errors import InvalidId

MAX_NB_FILES_PER_DIR = 400
PHOTO_SUBMISSION_FOLDERS = defaultdict()


class InitPM:
    def __init__(self, upload_folder, default_name):
        self.upload_folder = upload_folder
        self.default_name = default_name

    def submission_folder_dict(self):
        default_name = "aaaa"
        subfolders = [x[0] for x in os.walk(self.upload_folder)]
        subfolders = [d for d in subfolders if d != self.upload_folder]
        if len(subfolders) == 0:
            return {default_name: 0}

        folder_dict = {}
        for d in subfolders:
            nb_files = len([name for name in os.listdir(d) if
                            os.path.isfile(os.path.join(d, name))])
            folder_dict[os.path.basename(d)] = nb_files
        # push the smallest amount of photos in the submission folder up
        # the top
        FOLDERS = dict(sorted(folder_dict.items(), key=lambda item: item[0]))
        return FOLDERS

    def infer_current_submission_folder(self, folders_dict):
        k = self.default_name
        if len(folders_dict) == 0:
            return k
        for k in folders_dict:
            if folders_dict[k] < MAX_NB_FILES_PER_DIR:
                logging.info("Directory %s has  %s photos.", k, folders_dict[k])
                return k
        # Otherwise, it is starting a new series folder
        next_value = next_string(k)
        if next_value != "":
            try:
                os.makedirs(os.path.join(self.upload_folder, next_value),
                            exist_ok=True)
                folders_dict[next_value] = 0
            except FileExistsError as e:
                logging.error("Folder Exists! Use It! %s", e)
            except FileNotFoundError as e:
                logging.error("404: Folder Not Found %s", e)
            except OSError as error:
                logging.error("Directory %s can not be created due to %s.",
                              next_value, error)
            return next_value
        return self.default_name


# Function to return a default
# values for keys that is not present
def def_value():
    return "Not Present"


def hello():
    print("Hello World!")


# https://realpython.com/python-flatten-list/
def flatten_concatenation(matrix):
    flat_list = []
    for row in matrix:
        flat_list += row

    return flat_list


def create_buckets(all_photos, bucket_size):
    """
    counter = 0 -> the last bucket will have less or equal the number of
    photos than the bucket size
    counter = 1 -> the first bucket will have less or equal the number of
    photos than the bucket size
    """
    buckets = []
    counter = 0
    bucket = []
    i = 0
    b = 1

    for photo in all_photos:
        i += 1
        if counter == bucket_size:
            # REMEMBER: always adding the last photo to the current bucket!!!
            bucket.append(photo)
            buckets.append(bucket)
            # then reset the bucket and the counters
            bucket = []
            counter = 1
            b += 1
        else:
            bucket.append(photo)
            counter += 1

        # print("Bucket {} - Photo {}: {}".format(b, i, photo["filename"]))

    # append the last bucket regardless of no matter how it has
    if counter <= bucket_size:
        buckets.append(bucket)

    return buckets


def next_string(s):
    # aaaa, aaab, aaac, etc.
    # https://stackoverflow.com/a/932536/865603
    strip_zs = s.rstrip('z')
    if strip_zs:
        p1 = chr(ord(strip_zs[-1]) + 1)
        p2 = 'a' * (len(s) - len(strip_zs))
        return strip_zs[:-1] + p1 + p2
    return 'a' * (len(s) + 1)


def safe_convert(id_str):
    """
    Converts a valid 24-character hex string to an ObjectId

    To convert a string to an ObjectId in Python, you need to use the bson
    library, which is installed automatically when you install pymongo.
    """
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        print(f"Error: '{id_str}' is not a valid ObjectId.")
        return None
