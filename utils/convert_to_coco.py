# Produce JSON files for train/val/test splits in COCO format.

import argparse
import cv2
from itertools import groupby
import json
import numpy as np
import os
import pycococreatortools

def get_images_section(mask_sourcefile, image_dir):
  images = []
  im_id_dict = {}
  # image IDs are non-unique because could have multiple classes
  counter = 1
  with open(mask_sourcefile, 'r') as f:
    next(f) # skip header
    for line in f:
      _, im_id, _, _, _, _, _, _, _, _ = line.strip().split(',')
      if im_id not in im_id_dict:
        im_filename = '{}.jpg'.format(im_id)
        im = cv2.imread(os.path.join(image_dir, im_filename))
        height = im.shape[0]
        width = im.shape[1]

        images.append(
          {
            'file_name': im_filename,
            'height': height,
            'width': width,
            'id': counter
          }
        )
        im_id_dict[im_id] = {'id': counter, 'height': height, 'width': width}
        counter += 1

  print('Generated images section.')
  return images, im_id_dict

def get_categories_section(category_sourcefile):
  categories = []
  category_dict = {}
  # Two fields: CategoryId,CategoryName (but no header in file)
  with open(category_sourcefile, 'r') as f:
    counter = 1
    for line in f:
      class_id, class_name = line.strip().split(',')
      categories.append(
        {
          'id': counter,
          'name': class_name,     # e.g. "doughnut"
          'original_id': class_id, # e.g. "/m/0jy4k"
          'supercategory': 'shape'
        }
      )
      category_dict[class_id] = counter
      counter += 1

  print('Generated categories section.')
  return categories, category_dict

def get_bbox_dict(bbox_sourcefile):
  # First get "isGroupOf" information. Key is ImageID, LabelName, XMin (rounded to 2 decimals) concatenated together
  bbox_group_dict = {}
  with open(bbox_sourcefile, 'r') as f:
    next(f) # Skip header line
    for line in f:
      image_id, label_name, x_min, _, _, _, is_group_of = line.strip().split(',')
      # Rounding is necessary because the decimal precision of the bounding box coordinates differs between files...
      key = image_id + '_' + label_name + '_' + str(round(float(x_min), 2))
      bbox_group_dict[key] = int(is_group_of)
  print('Generated IsGroupOf dictionary.')
  return bbox_group_dict

def binary_mask_to_rle(binary_mask):
  rle = {'counts': [], 'size': list(binary_mask.shape)}
  counts = rle.get('counts')
  for i, (value, elements) in enumerate(groupby(binary_mask.ravel(order='F'))):
    if i == 0 and value == 1:
      counts.append(0)
    counts.append(len(list(elements)))

  return rle

def get_annotations_section(mask_sourcefile, mask_dir, im_id_dict, category_dict):
  # Key is ImageID, LabelName, XMin (rounded to 2 decimals) concatenated together
  annotations = []

  # Ten fields: MaskPath,ImageID,LabelName,BoxID,BoxXMin,BoxXMax,BoxYMin,BoxYMax,PredictedIoU,Clicks
  counter = 1
  with open(mask_sourcefile, 'r') as f:
    next(f) # Skip header line
    for line in f:
      mask_path, image_filename, label_name, _, x_min, x_max, y_min, y_max, _, _ = line.strip().split(',')
      subset = mask_dir.split('/')[-1]
      mask_sub_folder = '{}-masks-{}'.format(subset, mask_path[0]) # e.g. validation-masks-a
      mask_path = os.path.join(mask_dir, mask_sub_folder, mask_path)
      binary_mask = cv2.imread(mask_path, 0).astype(np.uint8)

      category_id = category_dict[label_name] # Maps class/label name to integer
      image_id = im_id_dict[image_filename]['id'] # alphanumerical string -> integer
      if image_filename not in im_id_dict:
        print(image_filename)
      category_info = {'id': category_id, 'is_crowd': 0}
      # Resize mask to image size
      im_width = im_id_dict[image_filename]['width']
      im_height = im_id_dict[image_filename]['height']
      binary_mask = cv2.resize(binary_mask, (im_width, im_height))
      assert(binary_mask.shape == (im_height, im_width))

      annotation_info = pycococreatortools.create_annotation_info(counter, image_id, category_info, binary_mask)
      if annotation_info is not None:
        annotations.append(annotation_info)
      counter += 1

    print('Generated annotations section.')
    return annotations

if __name__ == "__main__":
  parser = argparse.ArgumentParser(description='Convert OpenImages annotations into COCO format')
  parser.add_argument('-p', '--path', help='Path to OpenImages dataset', type=str, required=True)
  parser.add_argument('-s', '--subset', help="'train' or 'validation'", type=str, required=True)
  args = vars(parser.parse_args())

  root_dir = args['path']
  subset = args['subset']
  assert(subset == 'train' or subset == 'validation')

  annotation_dir = os.path.join(root_dir, 'annotations')
  image_dir = os.path.join(root_dir, 'images', subset)
  mask_dir = os.path.join(root_dir, 'masks', subset)
  category_sourcefile = os.path.join(annotation_dir, 'challenge-2019-classes-description-segmentable.csv')
  mask_sourcefile = os.path.join(annotation_dir, 'challenge-2019-{}-segmentation-masks.csv'.format(subset))

  dataset = {}
  dataset['info'] = {}
  dataset['licenses'] = {}
  dataset['images'], im_id_dict = get_images_section(mask_sourcefile, image_dir)
  dataset['categories'], category_dict = get_categories_section(category_sourcefile)
  dataset['annotations'] = get_annotations_section(mask_sourcefile, mask_dir, im_id_dict, category_dict)

  output_file = os.path.join(annotation_dir, '{}_coco.json'.format(subset))
  with open(output_file, 'w') as f:
    json.dump(dataset, f)
  print('Finished generating {} COCO file.'.format(subset))
