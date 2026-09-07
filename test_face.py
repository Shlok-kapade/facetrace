import urllib.request
import face_recognition

urllib.request.urlretrieve("https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcRB57l7rt9sxVeBs7JtCfp_816N_teeeQritvuyUjUPNJmeGiXE", "test.jpg")
image = face_recognition.load_image_file("test.jpg")
locs = face_recognition.face_locations(image)
print("HOG faces:", len(locs))
