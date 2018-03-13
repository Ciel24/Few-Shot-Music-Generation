#!/usr/bin/python3
import os
import time
import logging
import yaml

import numpy as np

from midi_loader import MIDILoader
from lyrics_loader import LyricsLoader
from dataset import Dataset, Metadata


class Episode(object):
    def __init__(self, support, query):
        self.support = support
        self.query = query


class SQSampler(object):
    """A sampler for randomly sampling support/query sets.

    Arguments:
        support_size (int): number of songs in the support set
        query_size (int): number of songs in the query set
    """
    def __init__(self, support_size, query_size):
        self.support_size = support_size
        self.query_size = query_size

    def sample(self, artist):
        sample = np.random.choice(
            artist,
            size=self.support_size+self.query_size,
            replace=False)
        query = sample[:self.query_size]
        support = sample[self.query_size:]
        return query, support


class EpisodeSampler(object):
    def __init__(self, dataset, batch_size, support_size, query_size, max_len, dtype=np.int32):
        self.dataset = dataset
        self.batch_size = batch_size
        self.support_size = support_size
        self.query_size = query_size
        self.max_len = max_len
        self.dtype = dtype
        self.sq_sampler = SQSampler(support_size, query_size)

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        return 'EpisodeSampler("%s", "%s")' % (self.root, self.split)

    def get_episode(self):
        support = np.zeros((self.batch_size, self.support_size, self.max_len), dtype=self.dtype)
        query = np.zeros((self.batch_size, self.query_size, self.max_len), dtype=self.dtype)
        artists = np.random.choice(self.dataset, size=self.batch_size, replace=False)
        for batch_index, artist in enumerate(artists):
            support_songs, query_songs = self.sq_sampler.sample(artist)
            for support_index, song in enumerate(support_songs):
                parsed_song = self.dataset.load(artist.name, song)
                support[batch_index,support_index,:] = parsed_song
            for query_index, song in enumerate(query_songs):
                parsed_song = self.dataset.load(artist.name, song)
                query[batch_index,query_index,:] = parsed_song
        return Episode(support, query)

def load_sampler_from_config(config):
    """Create an EpisodeSampler from a yaml config."""
    if isinstance(config, str):
        config = yaml.load(open(config, 'r'))
    else:
        config = yaml.load(config)
    required_keys = [
        'dataset_path',
        'query_size',
        'support_size',
        'batch_size',
        'max_len',
        'dataset',
        'split'
    ]
    optional_keys = [
        'train_proportion',
        'val_proportion',
        'test_proportion',
        'persist',
        'cache'
    ]
    for key in required_keys:
        if key not in config:
            raise RuntimeError('required config key "%s" not found' % key)
    props = (
        config.get('train_proportion', 8),
        config.get('val_proportion', 1),
        config.get('test_proportion', 1)
    )
    root = config['dataset_path']
    metadata_dir = 'few_shot_metadata_%s_%s' % (config['dataset'], config['max_len'])
    metadata = Metadata(root, metadata_dir)
    if config['dataset'] == 'lyrics':
        loader = LyricsLoader(config['max_len'], metadata=metadata)
        parallel = False
    elif config['dataset'] == 'midi':
        loader = MIDILoader(config['max_len'])
        parallel = True
    else:
        raise RuntimeError('unknown dataset "%s"' % config['dataset'])
    dataset = Dataset(
        root,
        config['split'],
        loader,
        metadata,
        split_proportions=props,
        cache=config.get('cache', True),
        persist=config.get('persist', True),
        validate=config.get('validate', True),
        min_songs=config['support_size']+config['query_size'],
        parallel=parallel
    )
    return EpisodeSampler(
        dataset,
        config['batch_size'],
        config['support_size'],
        config['query_size'],
        config['max_len'])
