# INTRO
I went through this [tutorial](https://www.digitalocean.com/community/tutorials/how-to-use-mongodb-in-a-flask-application) to create an app with Flask and MongoDB.

# START
```
export FLASK_APP=app
export FLASK_ENV=development
flask run
```

Alternatively, run `start.sh` as the wrapper. 

# DEMOS
* [Show photo(s) with hash_md5 (len=32)](http://127.0.0.1:5000/photo/show/d99eb2f04657b0449deaea945964d09e)
* [Delete a pho with its object id (len=24)](http://127.0.0.1:5000/photo/delete/66ca53aec984beddd47aa900)

# DOCS & IDEAS
[1] [Storing Large Amount of Files On File System](https://stackoverflow.com/questions/1576272/storing-large-number-of-files-in-file-system)

[2] [Storing a large amount of images](https://stackoverflow.com/questions/446358/storing-a-large-number-of-images)

[3] [HDD 1TB - How to store thousands of small files](https://www.reddit.com/r/hardware/comments/eyezd/hdd_1tb_how_to_store_thousands_of_small_files_eg/)

[4] [File Storage and Backup Best Practices](https://blogs.gwu.edu/himmelfarb/2022/11/23/file-storage-and-backup-best-practices/)