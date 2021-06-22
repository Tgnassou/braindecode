# Authors: Theo Gnassounou <theo.gnassounou@inria.fr>
#          Omar Chehab <l-emir-omar.chehab@inria.fr>
#
# License: BSD (3-clause)

import numpy as np
import torch
from torch import nn
from torch.nn import init
from torch.nn.functional import elu, upsample
from torch.nn.modules.batchnorm import BatchNorm1d


# TODO: check extra params

class USleep(nn.Module):

    def __init__(self, 
                 n_classes=5,
                 depth=12,
                 dilation=1,
                 dense_classifier_activation="tanh",
                 kernel_size=9,
                 transition_window=1,
                 filters_init=5,
                 complexity_factor=2):
        '''TODO: remove redundant arguments.'''
        super().__init__()

        # Set attributes
        padding = (kernel_size - 1) // 2   # to preserve dimension (check)
    
        # Instantiate encoder : input has shape (B, C, T)
        encoder = []
        filters = filters_init
        for _ in range(depth):
            # update nb of input / output channels
            in_channels = 2 if _ == 0 else out_channels
            out_channels = int(filters * complexity_factor)

            # add encoder block (down)
            encoder += [
                nn.Sequential(
                    nn.Conv1d(in_channels=in_channels, 
                              out_channels=out_channels, 
                              kernel_size=kernel_size, 
                              stride=1, 
                              padding=padding),
                    nn.ELU(),
                    nn.BatchNorm1d(num_features=out_channels),
                )
            ]
            
            # update nb of filters
            filters = int(filters * np.sqrt(2))
        self.encoder = nn.Sequential(*encoder)

        # Instantiate bottom
        in_channels = out_channels
        out_channels = int(filters * complexity_factor)
        bottom = nn.Sequential(
                    nn.Conv1d(in_channels=in_channels, 
                              out_channels=out_channels, 
                              kernel_size=kernel_size, 
                              stride=1, 
                              padding=padding),
                    nn.ELU(),
                    nn.BatchNorm1d(num_features=out_channels),
                )

        # Instantiate decoder
        decoder_preskip = []
        decoder_postskip = []

        for _ in range(depth):

            # add decoder blocks (up)
            decoder_preskip += [
                nn.Sequential(
                    nn.Upsample(scale_factor=2),
                    nn.Conv1d(in_channels=in_channels, 
                              out_channels=out_channels, 
                              kernel_size=kernel_size, 
                              stride=1, 
                              padding=(kernel_size - 1) // 2),
                    nn.ELU(),
                    nn.BatchNorm1d(num_features=out_channels),
                )
            ]
            
            # we will concatenate channels via a skip connection, so they multiply by 2
            in_channels *= 2

            # add encoder block (down)
            decoder_postskip += [
                nn.Sequential(
                    nn.Conv1d(in_channels=in_channels, 
                              out_channels=out_channels, 
                              kernel_size=kernel_size, 
                              stride=1, 
                              padding=(kernel_size - 1) // 2),  # to preserve dimension (check)
                    nn.ELU(),
                    nn.BatchNorm1d(num_features=out_channels),
                )
            ]

        self.decoder_preskip = nn.Sequential(*decoder_preskip)
        self.decoder_postskip = nn.Sequential(*decoder_postskip)


    def forward(self, x):
        '''Input x has shape (B, C, T).'''
        
        # encoder
        residuals = []
        for down in self.encoder:
            x = down(x)
            residuals.append(x)
            x = nn.MaxPool1d(kernel_size=2)(x)

        # decoder
        residuals = residuals[::-1]  # in order of up layers
        for (idx, (up_preskip, up_postskip)) in enumerate(zip(self.decoder_preskip, self.decoder_postskip)):
            x = up_preskip(x)
            x = torch.cat([x, residuals[idx]], axis=1) # (B, 2 * C, T)
            x = up_postskip(x)
        
        return x

    # self.clf = # 


# Small testing script
batch_size, n_channels, n_times = 1024, 2, 3000
x = torch.Tensor(batch_size, n_channels, n_times)
model = USleep()