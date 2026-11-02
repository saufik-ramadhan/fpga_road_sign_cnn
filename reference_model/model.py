"""Small float CNN whose operators can later map to integer RTL."""
import torch
from torch import nn


class SignCNN(nn.Module):
    def __init__(self, image_size=16, classes=8, filters=8):
        super().__init__()
        if image_size < 4 or (image_size - 2) % 2:
            raise ValueError('Use an even input size >= 4 for exact pooling')
        self.conv = nn.Conv2d(1, filters, 3, bias=True)
        self.pool = nn.MaxPool2d(2)
        self.fc = nn.Linear(filters * ((image_size - 2) // 2) ** 2, classes)

    def forward(self, x):
        return self.fc(self.pool(torch.relu(self.conv(x))).flatten(1))


def architecture_cost(image_size, classes=8, filters=8):
    features = filters * ((image_size - 2) // 2) ** 2
    weights = filters * 9 + features * classes
    return dict(features=features, weights=weights, biases=filters + classes,
                macs=filters * (image_size - 2) ** 2 * 9 + features * classes)
