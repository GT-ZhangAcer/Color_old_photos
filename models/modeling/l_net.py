# coding: utf8
# Copyright (c) 2019 PaddlePaddle Authors. All Rights Reserve.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import paddle.fluid as fluid
from models.libs.model_libs import scope
from models.libs.model_libs import bn_relu
from models.libs.model_libs import conv


def double_conv(data, out_ch):
    param_attr = fluid.ParamAttr(
        name='weights',
        regularizer=fluid.regularizer.L2DecayRegularizer(
            regularization_coeff=0.0),
        initializer=fluid.initializer.TruncatedNormal(loc=0.0, scale=0.33))
    with scope("conv0"):
        data = bn_relu(
            conv(data, out_ch, 3, stride=1, padding=1, param_attr=param_attr))
    with scope("conv1"):
        data = bn_relu(
            conv(data, out_ch, 3, stride=1, padding=1, param_attr=param_attr))
    return data


def down(data, out_ch):
    # 下采样：max_pool + 2个卷积
    with scope("down"):
        data = double_conv(data, out_ch)
    return data


def up(data, short_cut, out_ch):
    with scope("up"):
        data = fluid.layers.concat([data, short_cut], axis=1)
        data = double_conv(data, out_ch)
    return data


def encode(data):
    # 编码器设置
    short_cuts = []
    with scope("encode"):
        with scope("block1"):
            data = double_conv(data, 64)
            short_cuts.append(data)
        with scope("block2"):
            data = down(data, 64)
            short_cuts.append(data)
        with scope("block3"):
            data = down(data, 128)
            short_cuts.append(data)
        with scope("block4"):
            data = down(data, 128)
            short_cuts.append(data)
        with scope("block5"):
            data = down(data, 128)
    return data, short_cuts


def decode(data, short_cuts):
    # 解码器设置，与编码器对称
    with scope("decode"):
        with scope("decode1"):
            data = up(data, short_cuts[3], 128)
        with scope("decode2"):
            data = up(data, short_cuts[2], 128)
        with scope("decode3"):
            data = up(data, short_cuts[1], 64)
        with scope("decode4"):
            data = up(data, short_cuts[0], 64)
    return data


def get_logit(data, num_classes):
    # 根据类别数设置最后一个卷积层输出
    param_attr = fluid.ParamAttr(
        name='weights')
    d, s = encode(data)
    f = decode(d, s)
    with scope("logit"):
        data = conv(
            f, num_classes, 3, stride=1, padding=1, param_attr=param_attr)
    return data


if __name__ == '__main__':
    image_shape = [-1, 3, 320, 320]
    image = fluid.data(name='image', shape=image_shape, dtype='float32')
    logit = get_logit(image, 1)
    print("logit:", logit.shape)