import logging
import os
import re
import json
from os.path import expanduser
import pdb

import zipfile
import datetime
import tensorflow as tf
import numpy as np

from deepdrive_dataset.utils import mkdir_p
from deepdrive_dataset.deepdrive_dataset_download import DeepdriveDatasetDownload
from deepdrive_dataset.deepdrive_versions import DEEPDRIVE_LABELS
from deepdrive_dataset.tf_features import *
from PIL import Image


class DeepdriveDatasetWriter(object):
    feature_dict = {
        'image/height': None,
        'image/width': None,
        'image/shape': None,
        'image/object/bbox/id': None,
        'image/object/bbox/xmin': None,
        'image/object/bbox/xmax': None,
        'image/object/bbox/ymin': None,
        'image/object/bbox/ymax': None,
        'image/object/bbox/truncated': None,
        'image/object/bbox/occluded': None,
        'image/object/class/label/name': None,
        'image/object/class/label/id': None,
        'image/object/class/label': None,
        'image/encoded': None,
        'image/format': None,
        'image/id': None,
        'image/source_id': None,
        'image/filename': None,
    }

    @staticmethod
    def feature_dict_description(type='feature_dict'):
        """
        Get the feature dict. In the default case it is filled with all the keys and the items set to None. If the
        type=reading_shape the shape description required for reading elements from a tfrecord is returned)
        :param type: (anything = returns the feature_dict with empty elements, reading_shape = element description for
        reading the tfrecord files is returned)
        :return:
        """
        obj = DeepdriveDatasetWriter.feature_dict
        if type == 'reading_shape':
            obj['image/height'] = tf.FixedLenFeature((), tf.int64, 1)
            obj['image/width'] = tf.FixedLenFeature((), tf.int64, 1)
            obj['image/shape'] = tf.FixedLenFeature([3], tf.int64)
            obj['image/object/bbox/id'] = tf.VarLenFeature(tf.int64)
            obj['image/object/bbox/xmin'] = tf.VarLenFeature(tf.float32)
            obj['image/object/bbox/xmax'] = tf.VarLenFeature(tf.float32)
            obj['image/object/bbox/ymin'] = tf.VarLenFeature(tf.float32)
            obj['image/object/bbox/ymax'] = tf.VarLenFeature(tf.float32)
            obj['image/object/bbox/truncated'] = tf.VarLenFeature(tf.int64)
            obj['image/object/bbox/occluded'] = tf.VarLenFeature(tf.int64)
            obj['image/encoded'] = tf.FixedLenFeature((), tf.string, default_value='')
            obj['image/format'] = tf.FixedLenFeature((), tf.string, default_value='')
            obj['image/filename'] = tf.FixedLenFeature((), tf.string, default_value='')
            obj['image/id'] = tf.FixedLenFeature((), tf.string, default_value='')
            obj['image/source_id'] = tf.FixedLenFeature((), tf.string, default_value='')
            obj['image/object/class/label/id'] = tf.VarLenFeature(tf.int64)
            obj['image/object/class/label'] = tf.VarLenFeature(tf.int64)
            obj['image/object/class/label/name'] = tf.VarLenFeature(tf.string)
        return obj

    def __init__(self):
        self.input_path = os.path.join('/content', 'BDD')

    def unzip_file_to_folder(self, filename, folder, remove_file_after_creating=True):
        assert (os.path.exists(filename) and os.path.isfile(filename))
        assert (os.path.exists(folder) and os.path.isdir(folder))
        with zipfile.ZipFile(filename, 'r') as zf:
            zf.extractall(folder)
        if remove_file_after_creating:
            print('\nRemoving file: {0}'.format(filename))
            os.remove(folder)

    def get_image_label_folder(self, fold_type=None, version=None):
        """
        Returns the folder containing all images and the folder containing all label information
        :param fold_type:
        :param version:
        :return: Raises BaseExceptions if expectations are not fulfilled (List, List, bool (indicating new version)
        """
        assert (fold_type in ['train', 'test', 'val'])
        version = '100k' if version is None else version
        assert (version in ['100k', '10k'])

        download_folder = os.path.join(self.input_path, 'download')
        expansion_images_folder = os.path.join(self.input_path, 'images')
        expansion_labels_folder = os.path.join(self.input_path, 'labels')
        #
        if not os.path.exists(expansion_images_folder):
            mkdir_p(expansion_images_folder)
        if not os.path.exists(expansion_labels_folder):
            mkdir_p(expansion_labels_folder)

        #full_labels_path = os.path.join(expansion_labels_folder, 'bdd100k', 'labels', '100k')
        full_labels_path = os.path.join(expansion_labels_folder, 'bdd100k', 'labels')
        full_images_path = os.path.join(expansion_images_folder, 'bdd100k', 'images')
        if version in [None, '100k']:
            full_images_path = os.path.join(full_images_path, '100k', fold_type)
        else:
            full_images_path = os.path.join(full_images_path, '10k', fold_type)

        extract_files = True

        valid_folder_structure_old_format = (len(DeepdriveDatasetDownload.filter_folders(full_labels_path)) == 2 and \
                                             len(DeepdriveDatasetDownload.filter_files(full_images_path)) > 0)

        valid_folder_structure_new_format = (len(DeepdriveDatasetDownload.filter_files(full_labels_path)) == 2 and \
                                             len(DeepdriveDatasetDownload.filter_files(full_images_path)) > 0)

        if valid_folder_structure_old_format or valid_folder_structure_new_format:
            print('Do not check the download folder. Pictures seem to exist.')
            if fold_type != 'test' and valid_folder_structure_new_format:
                full_labels_path = os.path.join(full_labels_path, fold_type)

            extract_files = False
        elif os.path.exists(download_folder):
            files_in_directory = DeepdriveDatasetDownload.filter_files(download_folder, False, re.compile('\.zip$'))
            if len(files_in_directory) < 2:
                raise BaseException('Not enough files found in {0}. All files present: {1}'.format(
                    download_folder, files_in_directory
                ))
        else:
            mkdir_p(download_folder)
            raise BaseException('Download folder: {0} did not exist. It had been created. '
                                'Please put images, labels there.'.format(download_folder))

        if valid_folder_structure_new_format:
            full_labels_path = os.path.join(full_labels_path, '..')

        # unzip the elements
        if extract_files:
            print('Starting to unzip the files. This might not work for the new dataformat')
            # TODO: update for new data format
            self.unzip_file_to_folder(
                os.path.join(
                    download_folder, 'bdd100k_labels.zip'
                ),
                expansion_labels_folder, False)
            self.unzip_file_to_folder(
                os.path.join(download_folder, 'bdd100k_images.zip'),
                expansion_images_folder, False)

        if fold_type == 'test':
            return full_images_path, None, True

        #pdb.set_trace()
        return full_images_path, full_labels_path, valid_folder_structure_new_format

    def filter_boxes_from_annotation(self, annotations):
        """

        :param annotations:
        :return: boxes, attributes
        """
        box = []
        if annotations is None:
            return box
        attributes = annotations['attributes']
        for frame in annotations['frames']:
            for obj in frame['objects']:
                if 'box2d' in obj:
                    box.append(obj)
        return dict(boxes=box, attributes=attributes)

    def _get_boundingboxes(self, annotations_for_picture_id):
        boxid, xmin, xmax, ymin, ymax, label_id, label, truncated, occluded = \
            [], [], [], [], [], [], [], [], []
        if annotations_for_picture_id is None:
            return boxid, xmin, xmax, ymin, ymax, label_id, label, truncated, occluded
        assert (len(annotations_for_picture_id['frames']) == 1)
        for frame in annotations_for_picture_id['frames']:
            for obj in frame['objects']:
                if 'box2d' not in obj:
                    continue
                boxid.append(obj['id'])
                xmin.append(obj['box2d']['x1'])
                xmax.append(obj['box2d']['x2'])
                ymin.append(obj['box2d']['y1'])
                ymax.append(obj['box2d']['y2'])
                label.append(obj['category'])
                label_id.append(DEEPDRIVE_LABELS.index(obj['category']) + 1)
                attributes = obj['attributes']
                truncated.append(attributes.get('truncated'))
                occluded.append(attributes.get('occluded', False))
        return boxid, xmin, xmax, ymin, ymax, label_id, label, truncated, occluded

    def _get_boundingboxes_new_format(self, annotations_for_picture_id):
        boxid, xmin, xmax, ymin, ymax, label_id, label, truncated, occluded = \
            [], [], [], [], [], [], [], [], []
        if annotations_for_picture_id is None:
            return boxid, xmin, xmax, ymin, ymax, label_id, label, truncated, occluded
        scene_attributes = annotations_for_picture_id['attributes']
        for obj in annotations_for_picture_id['labels']:
            if 'box2d' not in obj:
                continue
            boxid.append(obj['id'])
            xmin.append(obj['box2d']['x1'])
            xmax.append(obj['box2d']['x2'])
            ymin.append(obj['box2d']['y1'])
            ymax.append(obj['box2d']['y2'])
            label.append(obj['category'])

            # get the class label based on the deepdrive_labels, note that be add + 1 in order to account for
            # class_label_id = 0 --> background
            class_label_id = DEEPDRIVE_LABELS.index(obj['category']) + 1
            label_id.append(class_label_id)

            attributes = obj['attributes']
            truncated.append(attributes.get('truncated', False))
            occluded.append(attributes.get('occluded', False))
            '''
            truncated.append(scene_attributes.get('truncated'))
            #truncated.append(scene_attributes.get('truncated', False))
            occluded.append(scene_attributes.get('occluded', False))
            '''
        return boxid, xmin, xmax, ymin, ymax, label_id, label, truncated, occluded

    def _get_tf_feature_dict(self, image_id, image_path, image_format, annotations, new_format=True):
        if not new_format:
            boxid, xmin, xmax, ymin, ymax, label_id, label, truncated, occluded = \
                self._get_boundingboxes(annotations)
        else:
            boxid, xmin, xmax, ymin, ymax, label_id, label, truncated, occluded = \
                self._get_boundingboxes_new_format(annotations)

        truncated = np.asarray(truncated)
        occluded = np.asarray(occluded)
        #pdb.set_trace()
        #print(truncated)

        # convert things to bytes
        label_bytes = [tf.compat.as_bytes(l) for l in label]
        truncated_int = [int(t) for t in truncated]
        occluded_int = [int(o) for o in occluded]
        im = Image.open(image_path)
        image_width, image_height = im.size
        #pdb.set_trace()
        #image_shape = tf.convert_to_tensor([image_height, image_width, 3])
        image_shape = [image_height, image_width, 3]
        image_filename = os.path.basename(image_path)
        image_fileid = re.search('^(.*)(\.jpg)$', image_filename).group(1)

        tmp_feat_dict = DeepdriveDatasetWriter.feature_dict
        tmp_feat_dict['image/id'] = bytes_feature(image_fileid)
        tmp_feat_dict['image/source_id'] = bytes_feature(image_fileid)
        tmp_feat_dict['image/height'] = int64_feature(image_height)
        tmp_feat_dict['image/width'] = int64_feature(image_width)
        tmp_feat_dict['image/shape'] = int64_feature(image_shape)
        with open(image_path, 'rb') as f:
            tmp_feat_dict['image/encoded'] = bytes_feature(f.read())
        tmp_feat_dict['image/format'] = bytes_feature(image_format)
        tmp_feat_dict['image/filename'] = bytes_feature(image_filename)
        tmp_feat_dict['image/object/bbox/id'] = int64_feature(boxid)
        tmp_feat_dict['image/object/bbox/xmin'] = float_feature(xmin)
        tmp_feat_dict['image/object/bbox/xmax'] = float_feature(xmax)
        tmp_feat_dict['image/object/bbox/ymin'] = float_feature(ymin)
        tmp_feat_dict['image/object/bbox/ymax'] = float_feature(ymax)
        tmp_feat_dict['image/object/bbox/truncated'] = int64_feature(truncated_int)
        tmp_feat_dict['image/object/bbox/occluded'] = int64_feature(occluded_int)
        tmp_feat_dict['image/object/class/label/id'] = int64_feature(label_id)
        tmp_feat_dict['image/object/class/label'] = int64_feature(label_id)
        tmp_feat_dict['image/object/class/label/name'] = bytes_feature(label_bytes)
        #pdb.set_trace()

        return tmp_feat_dict

    @staticmethod
    def get_annotation(picture_id, full_labels_path=None):
        """
        Returns the annotation for the given picture_id.
        This is the method for the old data-format
        :param picture_id:
        :param full_labels_path:
        :return:
        """
        if full_labels_path is None:
            return None
        with open(os.path.join(
                full_labels_path, picture_id + '.json'), 'r') as f:
            return json.loads(f.read())

    @staticmethod
    def get_annotations_dict_from_single_json(json_path):
        """
        Loads the annotations from the single json file.
        Returns a dict with the image-id as key with all the labels
        :param json_path:
        :return:
        """
        assert (os.path.exists(json_path))
        filename_regex = re.compile('^(.*)\.jpg$')
        with open(json_path, 'r') as f:
            obj_list = json.load(f)
        obj_annotation_dict = dict()
        for element in obj_list:
            tmp_filename = filename_regex.match(element['name']).groups()[0]
            obj_annotation_dict[tmp_filename] = element
        return obj_annotation_dict

    def _get_tf_feature(self, image_id, image_path, image_format, annotations, new_format=True):
        """
        Returns a tf.train.Features object for the given image_id
        :param image_id:
        :param image_path:
        :param image_format:
        :param annotations:
        :param new_format:
        :return:
        """
        feature_dict = self._get_tf_feature_dict(
            image_id, image_path, image_format, annotations, new_format)
        return tf.train.Features(feature=feature_dict)

    @staticmethod
    def get_output_file_name_template(output_path, fold_type, version, small_size=None,
                                      weather_type=None, scene_type=None, daytime_type=None):
        """
        Returns string with str template: iteration
        :param fold_type:
        :param version:
        :param small_size:
        :return:
        """
        extra_parts = ''
        if small_size is not None:
            extra_parts += 'number_of_files_{0}_'.format(small_size)
        if weather_type is not None:
            extra_parts += 'weather_{0}_'.format(weather_type)
        if scene_type is not None:
            extra_parts += 'scene_{0}_'.format(scene_type)
        if daytime_type is not None:
            extra_parts += 'daytime_{0}_'.format(daytime_type)
        return os.path.join(
            output_path,
            'output_{version}_{extra_parts}_{{iteration:06d}}.tfrecord'.format(
                version=fold_type + ('100k' if version is None else version),
                extra_parts=extra_parts
            )
        )

    def write_tfrecord(self, fold_type=None, version=None,
                       max_elements_per_file=1000, write_masks=False,
                       small_size=None, weather_type=None, scene_type=None,
                       daytime_type=None):
        """
        Method which opens the tf.Session and actually writes the files
        :param fold_type: 'train', 'val', 'test'
        :param version: '100k', '10k'
        :param max_elements_per_file: the number of elements per file,
        after this number of elements a new tfrecord file is created
        :param write_masks: unused flag
        :param small_size: Parameter to limit the number of files which shall be written to files.
        [E.g. to test overfitting] (default: None)
        :return:
        """
        logger = logging.getLogger(__name__)
        assert (small_size is None or (isinstance(small_size, int) and small_size > 0))
        output_path = os.path.join(self.input_path, 'tfrecord', version if version is not None else '100k', fold_type)
        if not os.path.exists(output_path):
            mkdir_p(output_path)

        full_images_path, full_labels_path, new_format = self.get_image_label_folder(fold_type, version)
        print("new?:", new_format)

        obj_annotation_dict = dict()
        if new_format and fold_type != 'test':
            label_file = os.path.join(
                full_labels_path, 'bdd100k_labels_images_{0}.json'.format(
                    fold_type))
            try:
                obj_annotation_dict = DeepdriveDatasetWriter.\
                    get_annotations_dict_from_single_json(label_file)
            except BaseException as e:
                logger.error('Error loading the label json from: {0} '
                             'Error: {1}'.format(label_file, str(e)))
                exit(-1)

        # get the files
        image_files = DeepdriveDatasetDownload.filter_files(full_images_path, True)
        if small_size is not None:
            logger.info('Limiting the number of files written to TFrecord files to {0} files'.format(small_size))
        if weather_type is not None:
            logger.info('Limit to weather-type: {0}'.format(weather_type))
        if scene_type is not None:
            logger.info('Limit to scene-type: {0}'.format(scene_type))
        if daytime_type is not None:
            logger.info('Limit to daytime-type: {0}'.format(daytime_type))

        image_filename_regex = re.compile('^(.*)\.(jpg)$')
        tfrecord_file_id, writer = 0, None
        tfrecord_filename_template = DeepdriveDatasetWriter.get_output_file_name_template(
            output_path, fold_type, version, small_size, weather_type,
            scene_type, daytime_type
        )
        write_counter = 0
        with tf.Session() as sess:
            sess.run(tf.global_variables_initializer())
            for file_counter, f in enumerate(image_files):
                if write_counter % max_elements_per_file == 0:
                    if writer is not None and write_counter != 0:
                        writer.close()
                        tfrecord_file_id += 1
                    tmp_filename_tfrecord = tfrecord_filename_template.format(iteration=tfrecord_file_id)
                    logger.info('{0}: Create TFRecord filename: {1} after processing {2}/{3} files'.format(
                        str(datetime.datetime.now()), tmp_filename_tfrecord, file_counter, len(image_files)
                    ))
                    writer = tf.python_io.TFRecordWriter(tmp_filename_tfrecord)
                elif write_counter % 250 == 0:
                    logger.info('\t{0}: Processed file: {1}/{2}'.format(
                        str(datetime.datetime.now()), file_counter, len(image_files)))
                # match the filename with the regex
                m = image_filename_regex.search(f)
                if m is None:
                    logger.info('Filename did not match regex: {0}. '
                                'Skipping file.'.format(f))
                    continue

                picture_id = m.group(1)
                # get the annotations for the given file
                if not new_format:
                    picture_id_annotations = DeepdriveDatasetWriter.get_annotation(
                        picture_id, full_labels_path=full_labels_path)
                else:
                    picture_id_annotations = obj_annotation_dict.get(picture_id, None)

                if picture_id_annotations is None:
                    continue
                attributes = picture_id_annotations.get('attributes', None)

                if weather_type is not None and \
                        attributes['weather'] != weather_type:
                    continue

                if scene_type is not None and \
                        attributes['scene'] != scene_type:
                    continue

                if daytime_type is not None and \
                        attributes['timeofday'] != daytime_type:
                    continue

                feature = self._get_tf_feature(
                    picture_id, os.path.join(full_images_path, f),
                    m.group(2), picture_id_annotations, new_format)
                example = tf.train.Example(features=feature)
                writer.write(example.SerializeToString())
                write_counter += 1

                # we leave it if enough files were written
                if small_size is not None and write_counter >= small_size:
                    break

            # Close the last files
            if writer is not None:
                writer.close()
