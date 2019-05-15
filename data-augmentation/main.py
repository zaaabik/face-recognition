import optparse
import os

import cv2
import dlib
import numpy as np
from PIL import Image
from imutils import face_utils
from imutils.face_utils import FACIAL_LANDMARKS_68_IDXS

parser = optparse.OptionParser()
parser.add_option("-f", "--folder")
parser.add_option("-p", "--percent", default=100)
(options, args) = parser.parse_args()
folder = options.folder

sep = os.path.sep

detector = dlib.get_frontal_face_detector()
predictor_data_path = '../shape_predictor_68_face_landmarks.dat'
predictor = dlib.shape_predictor(predictor_data_path)


def main():
    files = os.listdir(folder)
    files = files[:1]
    for file in files:
        full_path = folder + sep + file
        image = cv2.imread(full_path)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        rects = detector(gray, 0)
        for (i, rect) in enumerate(rects):
            shape = predictor(gray, rect)
            shape = face_utils.shape_to_np(shape)

            (lStart, lEnd) = FACIAL_LANDMARKS_68_IDXS["left_eye"]
            (rStart, rEnd) = FACIAL_LANDMARKS_68_IDXS["right_eye"]

            left_eye_pts = shape[lStart:lEnd]
            right_eye_pts = shape[rStart:rEnd]
            left_eye_center = left_eye_pts.mean(axis=0).astype("int")
            right_eye_center = right_eye_pts.mean(axis=0).astype("int")

            left_eye_end = shape[rStart]
            right_eye_start = shape[lEnd - 3]

            cv2.circle(image, tuple(left_eye_center), 2, (0, 255, 0), -1)
            cv2.circle(image, tuple(right_eye_center), 2, (0, 255, 0), -1)

            cv2.circle(image, tuple(right_eye_start), 2, (0, 255, 0), -1)
            cv2.circle(image, tuple(left_eye_end), 2, (0, 255, 0), -1)

            mouth_top = shape[51]
            cv2.circle(image, tuple(mouth_top), 2, (0, 255, 0), -1)

            nose_bottom = shape[33]
            cv2.circle(image, tuple(nose_bottom), 2, (0, 255, 0), -1)

            mustache_pos = np.mean(shape[[33, 51]], axis=0).astype('int')
            cv2.circle(image, tuple(mustache_pos), 2, (0, 0, 255), -1)

            chin = shape[1]
            print(chin)
            print(mustache_pos)
            cv2.circle(image, tuple(chin), 2, (255, 0, 0), -1)

            glasses = Image.open('filters/glasses.png')
            beard = Image.open('filters/beard.png').convert("RGBA")
            beard = beard.resize((shape[8][1] - shape[1][1]), beard.size[1])
            glasses_width = left_eye_center[0] - right_eye_center[0]

            glasses_width = int((glasses_width / 2.5) * 5)
            glasses_height = glasses_width // 2
            glasses = glasses.resize((glasses_width, glasses_height))

            face = Image.fromarray(image[:, :, ::-1])
            glasses_offset = right_eye_center[0] - int(glasses_width / 4.5), left_eye_center[1] - glasses_height // 2

            face.paste(glasses, glasses_offset, glasses)
            face.paste(beard, glasses_offset, beard)
            face.show()
            # Show the image
        # cv2.imshow("Output", image)
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
