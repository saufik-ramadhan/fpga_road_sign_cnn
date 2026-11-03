"""Small float CNN whose operators can later map to integer RTL."""
import torch
from torch import nn


class SignCNN(nn.Module):
    def __init__(self, image_size=16, classes=8, filters=8, second_conv=False):
        super().__init__()
        if image_size < 4 or (image_size - 2) % 2:
            raise ValueError('Use an even input size >= 4 for exact pooling')
        self.conv = nn.Conv2d(1, filters, 3, bias=True)
        self.pool = nn.MaxPool2d(2)
        self.conv2 = nn.Conv2d(filters, filters, 3, padding=1) if second_conv else None
        self.fc = nn.Linear(filters * ((image_size - 2) // 2) ** 2, classes)

    def forward(self, x):
        x = self.pool(torch.relu(self.conv(x)))
        if self.conv2 is not None:
            x = torch.relu(self.conv2(x))
        return self.fc(x.flatten(1))


def architecture_cost(image_size, classes=8, filters=8, second_conv=False):
    features = filters * ((image_size - 2) // 2) ** 2
    weights = filters * 9 + features * classes
    extra_weights = filters * filters * 9 if second_conv else 0
    return dict(features=features, weights=weights + extra_weights,
                biases=filters + classes + (filters if second_conv else 0),
                macs=filters * (image_size - 2) ** 2 * 9 + features * classes
                + features * filters * 9 * int(second_conv))
