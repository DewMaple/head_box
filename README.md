# Head Box
Detect tiny heads in image

# Installation

$ cd utils  && make && make hungarian && cd ..
$ python train.py --hypes hypes/lstm_rezoom.json --gpu 0 --logdir output


# Evaluation

$ python evaluate.py --weights output/overfeat_rezoom_2018_01_02_09.44/save.ckpt-100000 --test_boxes data/brainwash/val_boxes.json


# Tensorboard

$ tensorboard --logdir output