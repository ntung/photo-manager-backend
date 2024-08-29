#!/usr/bin/env python3
#-*- coding: utf-8 -*-
import hashlib
import os

import requests
import uuid

# import the MongoClient class of the PyMongo library
from pymongo import MongoClient, ReturnDocument

# import ObjectID from MongoDB's BSON library
# (use pip3 to install bson)
from bson import ObjectId


def download_save_image():
    img_url = ("https://scontent.flhr1-2.fna.fbcdn.net/v/t39.30808-6/456797640_122168154668133782_4442476498527671168_n"
               ".jpg?_nc_cat=110&ccb=1-7&_nc_sid=833d8c&_nc_ohc=Jil3bbXaYo4Q7kNvgH_dtip&_nc_ht=scontent.flhr1-2.fna&oh"
               "=00_AYDfF3KucL2RV4FrneHlWM9wUBHXIZqFoPFtR0CwQ4tZUg&oe=66CFF00A")
    img_url = (
        "https://scontent.flhr1-2.fna.fbcdn.net/v/t39.30808-6/456695100_10232212218352261_5748597674855465029_n.jpg"
        "?_nc_cat=102&ccb=1-7&_nc_sid=127cfc&_nc_ohc=p01GlNjbC1YQ7kNvgGdOe9w&_nc_ht=scontent.flhr1-2.fna&oh"
        "=00_AYBPGPf-NWdkMkE8qAox2i0MK62fjbaqzqsZzyof9yuA3Q&oe=66D00590")
    img_url = ("https://scontent.flhr1-1.fna.fbcdn.net/v/t39.30808-6/456406141_122167657232133782_5336542751530079681_n"
               ".jpg?_nc_cat=107&ccb=1-7&_nc_sid=833d8c&_nc_ohc=rBjXcYld-LAQ7kNvgE4Sqeo&_nc_ht=scontent.flhr1-1.fna&oh"
               "=00_AYABNpdsL1eunGYTIV0gSWVnmbwbJlV4lCy1ohNpfDZZNw&oe=66CFE27D")
    img_url = ("https://scontent-lhr8-1.xx.fbcdn.net/v/t39.30808-6/456459176_10222302455374329_8715846420532793352_n"
               ".jpg?_nc_cat=111&ccb=1-7&_nc_sid=f727a1&_nc_ohc=sE5iT2-HUe8Q7kNvgFUZsor&_nc_ht=scontent-lhr8-1.xx"
               "&_nc_gid=A0X-Xx9rQwF20iS5lQ41OKl&oh=00_AYAMu2l92viMsCKxYlD5WHvOgvngumHUJcoa5LGlwmiCbA&oe=66D66CA0")
    res = requests.get(img_url)
    print(res.status_code)
    # Request the image and save it:
    out_filename = str(uuid.uuid4())
    with open("tmp/" + out_filename + ".jpg", "wb") as f:
        f.write(res.content)
        hashMD5 = hashlib.md5(res.content).hexdigest()
        print(hashMD5)


def check_find_result():
    mongo_client = MongoClient('mongodb://localhost:27017')

    # create database and collection instances
    db = mongo_client.flask_db
    col = db["photos"]
    # 4adb01c0d1c361ca1b79fbe92db634f8 --> exists
    # 7da09a6d42d2d32cadcc3c8f82cef3a8 --> non-exists
    cursor = col.find_one({"hash_md5": "4adb01c0d1c361ca1b79fbe92db634f8"})
    if cursor is None:
        print("nothing found")
    else:
        print(cursor)
        if cursor.get('_id') is None:
            print("The Cursor is empty")
        else:
            print("The Cursor is not empty")


def update_mongodb_doc():
    # docs: https://kb.objectrocket.com/mongo-db/how-to-update-a-mongodb-document-in-python-356
    # create a client instance of the MongoClient class
    mongo_client = MongoClient('mongodb://localhost:27017')

    # create database and collection instances
    db = mongo_client.flask_db
    col = db["photos"]

    # see if the MongoDB collection has documents on it
    total_docs = col.count_documents({})
    print("{} collection has {} total documents.".format(col.name, str(total_docs)))
    # call the Collection class's methods using the db object

    try:
        # pass a doc's ObjectId to find exact doc match
        find_result = db["photos"].find_one(
            ObjectId("66cd552aeac91d7825fce042")
        )
    except NameError as err:
        find_result = None
        print(err, "-- Use pip3 to install bson")
        print("Import the 'ObjectId' class from the 'bson' library")

    # print the document's contents if found
    if find_result is not None and type(find_result) is dict:
        print("found doc: ", find_result)
        pretty(find_result)

    # change date to current date
    doc = col.find_one_and_update(
        {"_id": ObjectId("66cd552aeac91d7825fce042")},
        {
            "$set": {"title": "Monika Mishra - What a stunning model, actress and young lady!"}
        },
        upsert=True, return_document=ReturnDocument.AFTER
    )
    print(doc)
    # print the document's contents if found
    # if find_result is not None and type(find_result) is dict:
    #     print("found doc:", find_result)


def pretty(d, indent=0):
    for key, value in d.items():
        print('\t' * indent + str(key))
        if isinstance(value, dict):
            pretty(value, indent + 1)
        else:
            print('\t' * (indent + 1) + str(value))


def get_date_created_n_modified_then_update_db_photos():
    import datetime
    import glob
    import pathlib

    # create database and collection instances
    mongo_client = MongoClient('mongodb://localhost:27017')
    db = mongo_client.flask_db
    col = db["photos"]

    photos_path = "/Users/tnguyen/MyBusiness/data/photo-manager/aaaa/"
    files = glob.glob(photos_path + "*.jpg")
    # print(files)
    arr_files = []
    for file in files:
        print(file)
        filename = os.path.basename(file)
        f_name = pathlib.Path(file)

        # get modification time
        m_timestamp = f_name.stat().st_mtime

        # convert ti to dd-mm-yyyy hh:mm:ss
        m_time = datetime.datetime.fromtimestamp(m_timestamp)
        arr_files.append({"filename": filename, "timestamp": m_time})
        doc = col.find({"filename": filename})

        # check md5
        hash_md5_str = ""
        md5_hash = hashlib.md5()
        with open(file, "rb") as f:
            # Read and update hash in chunks of 4K
            for byte_block in iter(lambda: f.read(4096), b""):
                md5_hash.update(byte_block)
            hash_md5_str = md5_hash.hexdigest()
        # print(doc)
        for photo in doc:
            # if photo is not None and "date_uploaded" not in photo and "date_modified" not in photo:
            if photo is not None and "hash_md5" not in photo:
                # print("created: date created and modified")
                print("updated hash md5")
                photo = col.update_one(
                    {"_id": photo.get("_id")},
                    {
                        # "$set": {
                        #     "date_uploaded": m_time,
                        #     "date_modified": m_time
                        # }
                        "$set": {
                            "hash_md5": hash_md5_str
                        }
                    },
                    upsert=False
                )
                print(photo)
            else:
                print("no need to be updated")


if __name__ == '__main__':
    # update_mongodb_doc()
    get_date_created_n_modified_then_update_db_photos()
    # download_save_image()
    # check_find_result()
