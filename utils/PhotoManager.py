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
