#!/usr/bin/env bash
: <<'END'
curl -X POST \
  -H "Submission-Folder: aaaa" \
  -H "Title: What a stunning model" \
  -H "Description: She looks so beautiful!" \
  -H "Courtesy: https://www.facebook.com/photo/?fbid=122161434128133782&set=a.122100011174133782" \
  -F file=@/Users/tnguyen/Music/FBVideos/451845670_122161434170133782_9141442333876530996_n.jpg \
  http://localhost:5000/photo/upload
END
: <<'END'
curl -s -X GET \
  -H "Accept: application/json" \
  http://localhost:5000/albums | jq
END

#   http://localhost:5000/albums/zhao-zhi
# curl -s -X GET http://127.0.0.1:7000/biomodels/services/download/get-files/MODEL1901160001/3/BIOMD0000000578_url.xml
curl -s -X GET http://127.0.0.1:5000/photo/aaaa/456713969_122167976138133782_3718382245528688943_n.jpg
# curl -s -X GET http://0.0.0.0:5000/photo/aaaa/myfile.txt

# -k meaning ignore SSL
curl -i -k -X POST -H "Content-Type: multipart/form-data" \
  -F "file=@z6948554753092_7e30301e49b8c903136fabccc45ec8f4.jpg" \
  -F 'metadata={}' https://192.168.0.210:5500/photo/upload