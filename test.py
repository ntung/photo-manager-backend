import requests
import uuid

img_url = ("https://scontent.flhr1-2.fna.fbcdn.net/v/t39.30808-6/456797640_122168154668133782_4442476498527671168_n"
           ".jpg?_nc_cat=110&ccb=1-7&_nc_sid=833d8c&_nc_ohc=Jil3bbXaYo4Q7kNvgH_dtip&_nc_ht=scontent.flhr1-2.fna&oh"
           "=00_AYDfF3KucL2RV4FrneHlWM9wUBHXIZqFoPFtR0CwQ4tZUg&oe=66CFF00A")
img_url = ("https://scontent.flhr1-2.fna.fbcdn.net/v/t39.30808-6/456695100_10232212218352261_5748597674855465029_n.jpg"
           "?_nc_cat=102&ccb=1-7&_nc_sid=127cfc&_nc_ohc=p01GlNjbC1YQ7kNvgGdOe9w&_nc_ht=scontent.flhr1-2.fna&oh"
           "=00_AYBPGPf-NWdkMkE8qAox2i0MK62fjbaqzqsZzyof9yuA3Q&oe=66D00590")
img_url = ("https://scontent.flhr1-1.fna.fbcdn.net/v/t39.30808-6/456406141_122167657232133782_5336542751530079681_n"
           ".jpg?_nc_cat=107&ccb=1-7&_nc_sid=833d8c&_nc_ohc=rBjXcYld-LAQ7kNvgE4Sqeo&_nc_ht=scontent.flhr1-1.fna&oh"
           "=00_AYABNpdsL1eunGYTIV0gSWVnmbwbJlV4lCy1ohNpfDZZNw&oe=66CFE27D")
res = requests.get(img_url)
print(res.status_code)
# Request the image and save it:
out_filename = str(uuid.uuid4())
with open("tmp/" + out_filename + ".jpg", "wb") as f:
    f.write(res.content)
