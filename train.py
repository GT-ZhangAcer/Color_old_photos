# Author: Acer Zhang
# Datetime:2020/7/6 19:37
# Copyright belongs to the author.
# Please indicate the source for reprinting.
import os
import time

import numpy as np
import paddle.fluid as fluid

from models.libs.model_libs import scope
from models.modeling.l_net import l_net
from data_reader import reader

LOAD_CHECKPOINT = False
LOAD_PER_MODEL = False
FREEZE = False

ROOT_PATH = "./"
TRAIN_DATA_PATH = os.path.join(ROOT_PATH, "data/train")
TEST_DATA_PATH = os.path.join(ROOT_PATH, "data/test")
CHECK_POINT_DIR = os.path.join(ROOT_PATH, "check_point/check_model.color")
PER_MODEL_DIR = os.path.join(ROOT_PATH, "data/unet_coco_v3")
MODEL_DIR = os.path.join(ROOT_PATH, "best_model.color")

EPOCH = 5
BATCH_SIZE = 1  # 与数据增强后分组大小一致
SIGNAL_A_NUM = 19
SIGNAL_B_NUM = 20

BOUNDARIES = [10000, 15000, 50000, 100000]
VALUES = [0.005, 0.001, 0.0005, 0.0001, 0.00005]
WARM_UP_STEPS = 500
START_LR = 0.005
END_LR = 0.01

place = fluid.CUDAPlace(0)
places = fluid.cuda_places()
exe = fluid.Executor(place)

train_program = fluid.Program()
start_program = fluid.Program()

with fluid.program_guard(train_program, start_program):
    # 训练输入层定义
    # 缩放后数据以及原始数据的灰度图像
    resize_l = fluid.data(name="resize_l", shape=[-1, 1, -1, -1])

    # LAB三通道
    img_l = fluid.data(name="img_l", shape=[-1, 1, -1, -1])
    label_a = fluid.data(name="label_a", shape=[-1, 1, -1, -1], dtype="int64")
    label_b = fluid.data(name="label_b", shape=[-1, 1, -1, -1], dtype="int64")

    # 获得shape参数
    im_shape = fluid.layers.shape(resize_l)
    im_shape = fluid.layers.slice(im_shape, axes=[0], starts=[2], ends=[4])
    fluid.layers.Print(im_shape)

    with scope("signal_l"):
        signal_l = l_net(resize_l, im_shape, 1)
    with scope("signal_a"):
        signal_a = l_net(img_l, im_shape, SIGNAL_A_NUM) if not FREEZE else l_net(signal_l, im_shape, SIGNAL_A_NUM)
    with scope("signal_b"):
        signal_b = l_net(img_l, im_shape, SIGNAL_B_NUM) if not FREEZE else l_net(signal_l, im_shape, SIGNAL_B_NUM)

    loss_l = fluid.layers.mse_loss(signal_l, img_l)
    cost_a_o, signal_a = fluid.layers.softmax_with_cross_entropy(signal_a, label_a, axis=1, return_softmax=True)
    cost_b_o, signal_b = fluid.layers.softmax_with_cross_entropy(signal_b, label_b, axis=1, return_softmax=True)

    cost_ab = cost_a_o + cost_b_o
    loss_ab = fluid.layers.mean(cost_ab)

    test_program = train_program.clone(for_test=True)
    signal_a_out = fluid.layers.argmax(x=signal_a, axis=1)
    signal_b_out = fluid.layers.argmax(x=signal_b, axis=1)

    # cost_a = fluid.layers.elementwise_mul(cost_a_o, w_a)
    # cost_b = fluid.layers.elementwise_mul(cost_b_o, w_b)
    # loss_a = fluid.layers.mean(cost_a)
    # loss_b = fluid.layers.mean(cost_b)

    learning_rate = fluid.layers.piecewise_decay(boundaries=BOUNDARIES, values=VALUES)
    decayed_lr = fluid.layers.linear_lr_warmup(learning_rate,
                                               WARM_UP_STEPS,
                                               START_LR,
                                               END_LR)
    opt = fluid.optimizer.Adam(decayed_lr)
    opt.minimize(loss_l)
    opt.minimize(loss_ab)
    final_loss = loss_l + loss_ab

# train_loader = fluid.io.DataLoader.from_generator(feed_list=[resize_l, img_l, label_a, label_b],
#                                                   capacity=8,
#                                                   iterable=True,
#                                                   use_double_buffer=True,
#                                                   drop_last=True)
# train_loader.set_sample_generator(reader(TRAIN_DATA_PATH), batch_size=BATCH_SIZE, drop_last=True, places=places)
# test_loader = fluid.io.DataLoader.from_generator(feed_list=[resize_l, img_l, label_a, label_b],
#                                                  capacity=8,
#                                                  iterable=True,
#                                                  use_double_buffer=True,
#                                                  drop_last=True)
# test_loader.set_sample_generator(reader(TEST_DATA_PATH), batch_size=BATCH_SIZE, drop_last=True,places=places)
train_feeder = fluid.DataFeeder(place=place,
                                feed_list=[resize_l, img_l, label_a, label_b],
                                program=train_program)
test_feeder = fluid.DataFeeder(place=place,
                               feed_list=[resize_l, img_l, label_a, label_b],
                               program=test_program)
train_loader = train_feeder.decorate_reader(reader(TRAIN_DATA_PATH), multi_devices=True)
test_loader = test_feeder.decorate_reader(reader(TEST_DATA_PATH), multi_devices=True)

exe.run(start_program)

compiled_train_prog = fluid.CompiledProgram(train_program).with_data_parallel(loss_name=final_loss.name)
compiled_test_prog = fluid.CompiledProgram(test_program).with_data_parallel(share_vars_from=compiled_train_prog)
print("Net check --OK")
if os.path.exists(CHECK_POINT_DIR + ".pdopt") and LOAD_CHECKPOINT:
    fluid.io.load(train_program, CHECK_POINT_DIR, exe)


def if_exist(var):
    return os.path.exists(os.path.join(PER_MODEL_DIR, var.name))


if os.path.exists(PER_MODEL_DIR) and LOAD_PER_MODEL:
    fluid.io.load_vars(exe, PER_MODEL_DIR, train_program, predicate=if_exist)

MIN_LOSS = 10.
for epoch in range(EPOCH):
    out_loss_ab = list()
    out_loss_l = list()
    lr = None
    for data_id, data in enumerate(train_loader()):
        start_time = time.time()
        out = exe.run(program=compiled_train_prog,
                      feed=data,
                      fetch_list=[loss_ab, loss_l, decayed_lr])
        out_loss_ab.append(out[0][0])
        out_loss_l.append(out[1][0])
        lr = out[2]
        cost_time = time.time() - start_time
        if data_id % 50 == 0:
            print(epoch,
                  "-",
                  data_id,
                  "TRAIN:\t{:.6f}".format(sum(out_loss_ab) / len(out_loss_ab)),
                  "L_PSNR:{:.6f}".format(10 * np.log10(255 * 255 / sum(out_loss_l) / len(out_loss_l))),
                  "\tTIME:\t{:.4f}/s".format(cost_time / BATCH_SIZE),
                  "\tLR:", lr)
            out_loss_ab = []
            out_loss_l = []
            fluid.io.save(train_program, CHECK_POINT_DIR)
        if data_id % 500 == 500 - 1:
            out_loss_ab = []
            out_loss_l = []
            for data_t in test_loader():
                out = exe.run(program=compiled_test_prog,
                              feed=data,
                              fetch_list=[loss_ab, loss_l])
                out_loss_ab.append(out[0][0])
                out_loss_l.append(out[1][0])
            test_loss = sum(out_loss_ab) / len(out_loss_ab)
            if test_loss <= MIN_LOSS:
                MIN_LOSS = test_loss
                fluid.io.save_inference_model(dirname=MODEL_DIR,
                                              feeded_var_names=["img_l", "resize_l"],
                                              target_vars=[signal_l, signal_a_out, signal_b_out],
                                              executor=exe,
                                              main_program=train_program)

            print(epoch,
                  "TEST:\t{:.6f}".format(sum(out_loss_ab) / len(out_loss_ab)),
                  "L_PSNR:{:.8f}".format(10 * np.log10(255 * 255 / sum(out_loss_l) / len(out_loss_l))),
                  "\tMIN LOSS:\t{:.4f}".format(MIN_LOSS))
