#!/usr/bin/env bash

curl -X POST \
  -H "Submission-Folder: aaaa" \
  -H "Title: What a stunning model" \
  -H "Description: She looks so beautiful!" \
  -H "Photo-Courtesy: https://www.facebook.com/photo/?fbid=122161434128133782&set=a.122100011174133782" \
  -F file=@/Users/tnguyen/Music/FBVideos/451845670_122161434170133782_9141442333876530996_n.jpg \
  http://localhost:5000/upload