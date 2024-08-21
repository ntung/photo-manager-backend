#!/usr/bin/env bash

curl -X POST \
  -H "Submission-Folder: aaaa" \
  -F file=@/Users/tnguyen/Music/FBVideos/452191131_7969555339792015_8350281371770719685_n.jpg \
  http://localhost:5000/upload