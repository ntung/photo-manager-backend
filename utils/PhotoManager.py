import os
import logging
from collections import defaultdict

MAX_NB_FILES_PER_DIR = 400
global PHOTO_SUBMISSION_FOLDERS


# Function to return a default
# values for keys that is not present


def def_value():
    return "Not Present"


PHOTO_SUBMISSION_FOLDERS = defaultdict(def_value)


def hello():
    print("Hello World!")


# https://realpython.com/python-flatten-list/
def flatten_concatenation(matrix):
    flat_list = []
    for row in matrix:
        flat_list += row

    return flat_list


def create_buckets(all_photos, bucket_size):
    buckets = []
    """
    counter = 0 -> the last bucket will have less or equal the number of photos than the bucket size
    counter = 1 -> the first bucket will have less or equal the number of photos than the bucket size
    """
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
    # https://stackoverflow.com/questions/932506/how-can-i-get-the-next-string-in-alphanumeric-ordering-in-python
    strip_zs = s.rstrip('z')
    if strip_zs:
        return strip_zs[:-1] + chr(ord(strip_zs[-1]) + 1) + 'a' * (len(s) - len(strip_zs))
    else:
        return 'a' * (len(s) + 1)


def calculate_current_submission_folder(upload_folder):
    default_name = "aaaa"
    # subfolders = [f.path for f in os.scandir(upload_folder) if f.is_dir()]
    subfolders = [x[0] for x in os.walk(upload_folder)]
    subfolders = [d for d in subfolders if d != upload_folder]
    if len(subfolders) == 0:
        return default_name

    folder_n_files_dict = dict()
    for d in subfolders:
        nb_files = len([name for name in os.listdir(d) if os.path.isfile(os.path.join(d, name))])
        folder_n_files_dict[os.path.basename(d)] = nb_files

    # sorted_dict = collections.OrderedDict(sorted(folder_n_files_dict.items()))
    FOLDERS = dict(sorted(folder_n_files_dict.items(), key=lambda item: item[0]))
    print(FOLDERS)
    k = default_name
    for k in FOLDERS:
        print(k, FOLDERS[k])
        if FOLDERS[k] < MAX_NB_FILES_PER_DIR:
            return k
    next_value = next_string(k)
    if next_value != "":
        try:
            os.mkdirs(os.path.join(upload_folder, next_value), exist_ok=True)
        except FileExistsError as e:
            logging.error("Folder Exists! Use It!" + str(e))
        except FileNotFoundError as e:
            logging.error("404: Folder Not Found" + str(e))
        except OSError as error:
            logging.error("Directory '%s' can not be created due to '%s'."(next_value, str(error)))
        return next_value
    else:
        # return the default value
        return default_name
