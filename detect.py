"""
This file is designed for prediction of bounding boxes for a single image.
Predictions could be made in two ways: command line style or service style. Command line style denotes that one can
run this script from the command line and configure all options right in the command line. Service style allows
to call :func:`initialize` function once and call :func:`hot_predict` function as many times as it needed to.
"""
import glob
import json
import os
import random
import subprocess
from optparse import OptionParser
from os import path

import numpy as np
import tensorflow as tf
from PIL import Image, ImageDraw
from scipy.misc import imread, imresize, imsave

from train import build_forward
from utils.annolist import AnnotationLib as al
from utils.data_utils import Rotate90
from utils.train_utils import add_rectangles, rescale_boxes

if __package__ is None:
    import sys

    sys.path.append(path.abspath(path.join(path.dirname(__file__), path.pardir, 'detect-widgets/additional')))


def initialize(weights_path, hypes_path, options=None):
    """Initialize prediction process.
    All long running operations like TensorFlow session start and weights loading are made here.
    Args:
        weights_path (string): The path to the model weights file.
        hypes_path (string): The path to the hyperparameters file.
        options (dict): The options dictionary with parameters for the initialization process.
    Returns (dict):
        The dict object which contains `sess` - TensorFlow session, `pred_boxes` - predicted boxes Tensor,
          `pred_confidences` - predicted confidences Tensor, `x_in` - input image Tensor,
          `hypes` - hyperparametets dictionary.
    """

    H = prepare_options(hypes_path, options)
    if H is None:
        return None

    tf.reset_default_graph()
    x_in = tf.placeholder(tf.float32, name='x_in', shape=[H['image_height'], H['image_width'], 3])
    if H['use_rezoom']:
        pred_boxes, pred_logits, pred_confidences, pred_confs_deltas, pred_boxes_deltas \
            = build_forward(H, tf.expand_dims(x_in, 0), 'test', reuse=None)
        grid_area = H['grid_height'] * H['grid_width']
        pred_confidences = tf.reshape(
            tf.nn.softmax(tf.reshape(pred_confs_deltas, [grid_area * H['rnn_len'], H['num_classes']])),
            [grid_area, H['rnn_len'], H['num_classes']])
        if H['reregress']:
            pred_boxes = pred_boxes + pred_boxes_deltas
    else:
        pred_boxes, pred_logits, pred_confidences = build_forward(H, tf.expand_dims(x_in, 0), 'test', reuse=None)

    saver = tf.train.Saver()
    sess = tf.Session()
    sess.run(tf.global_variables_initializer())
    saver.restore(sess, weights_path)
    return {'sess': sess, 'pred_boxes': pred_boxes, 'pred_confidences': pred_confidences, 'x_in': x_in, 'hypes': H}


def hot_predict(image_path, parameters, to_json=True, verbose=False):
    """Makes predictions when all long running preparation operations are made.
    Args:
        image_path (string): The path to the source image.
        parameters (dict): The parameters produced by :func:`initialize`.
        to_json (bool):
        verbose (bool):
    Returns (Annotation):
        The annotation for the source image.
    """

    H = parameters.get('hypes', None)
    if H is None:
        return None

    # The default options for prediction of bounding boxes.
    options = H['evaluate']
    print('options is {}'.format(options))
    if 'pred_options' in parameters:
        # The new options for prediction of bounding boxes
        for key, val in parameters['pred_options'].items():
            options[key] = val

    # predict
    use_sliding_window = H.get('sliding_predict', {'enable': False}).get('enable', False)
    if use_sliding_window:
        if verbose:
            print('Sliding window mode on')
        print('Sliding prediction')
        return sliding_predict(image_path, parameters, to_json, H, options)
    else:
        if verbose:
            print('Sliding window mode off')
        print('Regular prediction')
        return regular_predict(image_path, parameters, to_json, H, options)


def calculate_medium_box(boxes):
    conf_sum = reduce(lambda t, b: t + b.score, boxes, 0)
    aggregation = {}
    for name in ['x1', 'y1', 'x2', 'y2']:
        aggregation[name] = reduce(lambda t, b: t + b.__dict__[name] * b.score, boxes, 0) / conf_sum

    new_box = al.AnnoRect(**aggregation)
    new_box.classID = boxes[0].classID
    new_box.score = conf_sum / len(boxes)
    return new_box


def non_maximum_suppression(boxes):
    conf = [box.score for box in boxes]
    ind = np.argmax(conf)
    if isinstance(ind, int):
        return boxes[ind]
    else:
        random.seed()
        num = random.randint(0, len(ind))
        return boxes[num]


def combine_boxes(boxes, iou_min, nms, verbose=False):
    neighbours, result = [], []
    for i, box in enumerate(boxes):
        cur_set = set()
        cur_set.add(i)
        for j, neigh_box in enumerate(boxes):
            iou_val = box.iou(neigh_box)
            if verbose:
                print(i, j, iou_val)
            if i != j and iou_val > iou_min:
                cur_set.add(j)

        if len(cur_set) == 0:
            result.append(box)
        else:
            for group in neighbours:
                if len(cur_set.intersection(group)) > 0:
                    neighbours.remove(group)
                    cur_set = cur_set.union(group)
            neighbours.append(cur_set)

    for group in neighbours:
        cur_boxes = [boxes[i] for i in group]
        if nms:
            medium_box = non_maximum_suppression(cur_boxes)
        else:
            medium_box = calculate_medium_box(cur_boxes)
        result.append(medium_box)

    return result


def shift_boxes(pred_anno_rects, margin):
    for box in pred_anno_rects:
        box.y1 += margin
        box.y2 += margin


def to_box(anno_rect, parameters):
    box = {}
    box['x1'] = anno_rect.x1
    box['x2'] = anno_rect.x2
    box['y1'] = anno_rect.y1
    box['y2'] = anno_rect.y2
    box['score'] = anno_rect.score
    if 'classID' in parameters:
        box['classID'] = parameters['classID']
    else:
        box['classID'] = anno_rect.classID
    return box


def scale_boxes(result, (height_scale, width_scale)):
    boxes = []
    for r in result:
        boxes.append({
            "x1": r['x1'] * width_scale,
            "x2": r['x2'] * width_scale,
            "y1": r['y1'] * height_scale,
            "y2": r['y2'] * height_scale,
            "score": r['score']
        })
    return boxes


def save_scaled_img(np_img, result, image_path):
    imsave(image_path, np_img)
    img = Image.open(image_path)
    d = ImageDraw.Draw(img)
    is_list = type(result) is list
    rects = result if is_list else result.rects
    for r in rects:
        if is_list:
            d.rectangle([r['x1'], r['y1'], r['x2'], r['y2']], outline=(255, 0, 0))
        else:
            d.rectangle([r.left(), r.top(), r.right(), r.bottom()], outline=(255, 0, 0))
    img.save(image_path)


def regular_predict(image_path, parameters, to_json, H, options):
    orig_img = imread(image_path)[:, :, :3]
    raw_height, raw_width, _ = orig_img.shape
    print('raw shape is {}'.format((raw_height, raw_width)))
    img = Rotate90.do(orig_img)[0] if 'rotate90' in H['data'] and H['data']['rotate90'] else orig_img
    img = imresize(img, (H['image_height'], H['image_width']), interp='cubic')
    np_pred_boxes, np_pred_confidences = parameters['sess']. \
        run([parameters['pred_boxes'], parameters['pred_confidences']], feed_dict={parameters['x_in']: img})

    image_info = {'path': image_path, 'original_shape': img.shape[:2], 'transformed': img}
    pred_anno = postprocess_regular(image_info, np_pred_boxes, np_pred_confidences, H, options)
    result = [r.writeJSON() for r in pred_anno] if to_json else pred_anno

    fname = image_path.split(os.sep)[-1]
    img_path = os.path.join(os.path.dirname(image_path), '{}_predicted.png'.format(fname))
    save_scaled_img(img, result, img_path)

    print('result boxes is: {}'.format(result))
    print('scale is {} '.format((float(raw_height) / H['image_height'], float(raw_width) / H['image_width'])))
    result = scale_boxes(result, (float(raw_height) / H['image_height'], float(raw_width) / H['image_width']))
    print('reverted boxes is: {}'.format(result))
    return result


def propose_slides(img_height, slide_height, slide_overlap):
    slides = []
    step = slide_height - slide_overlap
    for top in range(0, img_height - slide_height, step):
        slides.append((top, top + slide_height))
    # there is some space left which was not covered by slides; make slide at the bottom of image
    slides.append((img_height - slide_height, img_height))
    return slides


def sliding_predict(image_path, parameters, to_json, H, options):
    orig_img = imread(image_path)[:, :, :3]
    height, width, _ = orig_img.shape
    if options.get('verbose', False):
        print(width, height)

    sl_win_options = H['sliding_predict']
    assert (sl_win_options['window_height'] > sl_win_options['overlap'])
    slides = propose_slides(height, sl_win_options['window_height'], sl_win_options['overlap'])

    result = []
    for top, bottom in slides:
        bottom = min(height, top + sl_win_options['window_height'])
        if options.get('verbose', False):
            print('Slide: ', 0, top, width, bottom)

        img = orig_img[top:bottom, 0:width]
        img = Rotate90.do(img)[0] if 'rotate90' in H['data'] and H['data']['rotate90'] else img
        img = imresize(img, (H['image_height'], H['image_width']), interp='cubic')

        np_pred_boxes, np_pred_confidences = parameters['sess']. \
            run([parameters['pred_boxes'], parameters['pred_confidences']], feed_dict={parameters['x_in']: img})
        image_info = {'path': image_path, 'original_shape': (bottom - top, width), 'transformed': img,
                      'a': orig_img[top:bottom, 0:width]}

        pred_boxes = postprocess_regular(image_info, np_pred_boxes, np_pred_confidences, H, options)
        shift_boxes(pred_boxes, top)
        result.extend(pred_boxes)

    result = combine_boxes(result, sl_win_options['iou_min'], sl_win_options['nms'])
    result = [r.writeJSON() for r in result] if to_json else result
    print('result boxes is: {}'.format(result))
    return result


def postprocess_regular(image_info, np_pred_boxes, np_pred_confidences, H, options):
    pred_anno = al.Annotation()
    pred_anno.imageName = image_info['path']
    pred_anno.imagePath = os.path.abspath(image_info['path'])
    _, rects = add_rectangles(H, [image_info['transformed']], np_pred_confidences, np_pred_boxes, use_stitching=True,
                              rnn_len=H['rnn_len'], min_conf=options['min_conf'], tau=options['tau'],
                              show_suppressed=False)

    h, w = image_info['original_shape']
    if 'rotate90' in H['data'] and H['data']['rotate90']:
        # original image height is a width for rotated one
        rects = Rotate90.invert(h, rects)

    rects = [r for r in rects if r.x1 < r.x2 and r.y1 < r.y2 and r.score > options['min_conf']]

    pred_anno.rects = rects
    pred_anno = rescale_boxes((H['image_height'], H['image_width']), pred_anno, h, w)
    return pred_anno


def prepare_options(hypes_path='hypes.json', options=None):
    """Sets parameters of the prediction process. If evaluate options provided partially, it'll merge them.
    The priority is given to options argument to overwrite the same obtained from the hyperparameters file.
    Args:
        hypes_path (string): The path to model hyperparameters file.
        options (dict): The command line options to set before start predictions.
    Returns (dict):
        The model hyperparameters dictionary.
    """
    with open(hypes_path, 'r') as f:
        H = json.load(f)
    # set default options values if they were not provided
    if options is None:
        if 'evaluate' in H:
            options = H['evaluate']
        else:
            print ('Evaluate parameters were not found! You can provide them through hyperparameters json file '
                   'or hot_predict options parameter.')
            return None
    else:
        if 'evaluate' not in H:
            H['evaluate'] = {}
        # merge options argument into evaluate options from hyperparameters file
        for key, val in options.iteritems():
            if val is not None:
                H['evaluate'][key] = val

    if H['evaluate'].get('gpu', False):
        os.environ['CUDA_VISIBLE_DEVICES'] = str(H['evaluate']['gpu'])
    return H


def save_results(image_path, anno, output_dir, fname='result', json_result=False):
    """Saves results of the prediction.
    Args:
        image_path (string): The path to source image to predict bounding boxes.
        anno (Annotation, list): The predicted annotations for source image or the list of bounding boxes.
        json_result: if create json file of detected rects
    Returns:
        Nothing.
    """

    # draw
    new_img = Image.open(image_path)
    d = ImageDraw.Draw(new_img)
    is_list = type(anno) is list
    rects = anno if is_list else anno.rects
    for r in rects:
        if is_list:
            d.rectangle([r['x1'], r['y1'], r['x2'], r['y2']], outline=(255, 0, 0))
        else:
            d.rectangle([r.left(), r.top(), r.right(), r.bottom()], outline=(255, 0, 0))

    # save
    prediction_image_path = os.path.join(output_dir, fname + '.png')
    new_img.save(prediction_image_path)
    subprocess.call(['chmod', '644', prediction_image_path])

    if json_result:
        fpath = os.path.join(os.path.dirname(image_path), fname + '.json')
        if is_list:
            json.dump({'image_path': prediction_image_path, 'rects': anno}, open(fpath, 'w'))
        else:
            al.saveJSON(fpath, anno)
        subprocess.call(['chmod', '644', fpath])


def main():
    parser = OptionParser(usage='usage: %prog [options] <image> <hypes>')
    parser.add_option('--gpu', action='store', type='int', default=0)
    parser.add_option('--tau', action='store', type='float')
    parser.add_option('--min_conf', action='store', type='float')

    (options, args) = parser.parse_args()
    options = vars(options)

    if len(args) < 3:
        print ('Provide path configuration json file')
        return

    data_dir = args[0]
    hypes_path = args[1]
    output_dir = args[2]
    print(args)

    config = json.load(open(hypes_path, 'r'))
    weights_path = os.path.join(os.path.dirname(hypes_path), config['solver']['weights'])
    init_params = initialize(weights_path, hypes_path, options)
    init_params['pred_options'] = {'verbose': True}

    filenames = []
    for ext in ('*.png', '*.gif', '*.jpg', '*.jpeg'):
        filenames.extend(glob.glob(os.path.join(data_dir, ext)))

    print(filenames)
    for image_filename in filenames:
        pred_anno = hot_predict(image_filename, init_params)
        fname = image_filename.split(os.sep)[-1]

        save_results(image_filename, pred_anno, output_dir, fname)


if __name__ == '__main__':
    main()
