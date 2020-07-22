# Author: Acer Zhang
# Datetime:2020/7/6 21:39
# Copyright belongs to the author.
# Please indicate the source for reprinting.
import cv2 as cv
import paddle.fluid as fluid
from matplotlib import pyplot as plt

from data_reader import reader
from cvt_image_data import cvt_color

TEST_DATA_PATH = "./data/f"
MODEL_DIR = "./best_model.color"
DICT_PATH = "./Color1D.dict"

with open(DICT_PATH, "r", encoding="utf-8") as f:
    a_dict, b_dict = eval(f.read())[1]
IM_SIZE = [256] * 2

place = fluid.CPUPlace()
exe = fluid.Executor(place)

infer_reader = fluid.io.batch(
    reader=reader(TEST_DATA_PATH, is_val=True, im_size=IM_SIZE),
    batch_size=1)

program, feed_list, target_list = fluid.io.load_inference_model(dirname=MODEL_DIR, executor=exe)
feeder = fluid.DataFeeder(place=place, feed_list=feed_list, program=program)

for data in infer_reader():
    ipt_data = [i[0] for i in data]
    # ipt_l = [i[1] for i in data]
    ipt_h = [i[2] for i in data]
    ipt_w = [i[3] for i in data]
    out = exe.run(program, feeder.feed(ipt_data), fetch_list=target_list)
    for img_h, img_w, img_rl, img_a, img_b in zip(ipt_h, ipt_w, out[0], out[1], out[2]):
        img_l = img_rl.reshape((IM_SIZE[0] * 2, IM_SIZE[1] * 2)) * 255
        img_l = cv.resize(img_l.astype("uint8"), (img_w * 2, img_h * 2))
        tmp = cv.resize(img_l.astype("uint8"), (img_w, img_h))
        img_a = cvt_color(img_a, a_dict)
        img_b = cvt_color(img_b, b_dict)
        img_a_r = cv.resize(img_a.astype("uint8"), (img_w * 2, img_h * 2))
        img_b_r = cv.resize(img_b.astype("uint8"), (img_w * 2, img_h * 2))
        img = cv.merge([img_l.astype("uint8"), img_a_r, img_b_r])
        img = cv.cvtColor(img, cv.COLOR_LAB2BGR)
        img = cv.resize(img, (img_w, img_h))
        cv.imshow("f", img)
        cv.waitKey(0)
