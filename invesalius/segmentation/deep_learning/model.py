from collections import OrderedDict

import torch
import torch.nn as nn

SIZE: int = 48

class Unet3D(nn.Module):
    def __init__(self, in_channels: int = 1, out_channels: int = 1, init_features: int = 8) -> None:
        super().__init__()
        features: int = init_features

        self.encoder1: nn.Sequential = self._block(
            in_channels, features=features, padding=2, name="enc1"
        )
        self.pool1: nn.MaxPool3d = nn.MaxPool3d(kernel_size=2, stride=2)

        self.encoder2: nn.Sequential = self._block(
            features, features=features * 2, padding=2, name="enc2"
        )
        self.pool2: nn.MaxPool3d = nn.MaxPool3d(kernel_size=2, stride=2)

        self.encoder3: nn.Sequential = self._block(
            features * 2, features=features * 4, padding=2, name="enc3"
        )
        self.pool3: nn.MaxPool3d = nn.MaxPool3d(kernel_size=2, stride=2)

        self.encoder4: nn.Sequential = self._block(
            features * 4, features=features * 8, padding=2, name="enc4"
        )
        self.pool4: nn.MaxPool3d = nn.MaxPool3d(kernel_size=2, stride=2)

        self.bottleneck: nn.Sequential = self._block(
            features * 8, features=features * 16, padding=2, name="bottleneck"
        )

        self.upconv4: nn.ConvTranspose3d = nn.ConvTranspose3d(
            features * 16, features * 8, kernel_size=4, stride=2, padding=1
        )
        self.decoder4: nn.Sequential = self._block(
            features * 16, features=features * 8, padding=2, name="dec4"
        )

        self.upconv3: nn.ConvTranspose3d = nn.ConvTranspose3d(
            features * 8, features * 4, kernel_size=4, stride=2, padding=1
        )
        self.decoder3: nn.Sequential = self._block(
            features * 8, features=features * 4, padding=2, name="dec4"
        )

        self.upconv2: nn.ConvTranspose3d = nn.ConvTranspose3d(
            features * 4, features * 2, kernel_size=4, stride=2, padding=1
        )
        self.decoder2: nn.Sequential = self._block(
            features * 4, features=features * 2, padding=2, name="dec4"
        )

        self.upconv1: nn.ConvTranspose3d = nn.ConvTranspose3d(
            features * 2, features, kernel_size=4, stride=2, padding=1
        )
        self.decoder1: nn.Sequential = self._block(
            features * 2, features=features, padding=2, name="dec4"
        )

        self.conv: nn.Conv3d = nn.Conv3d(
            in_channels=features, out_channels=out_channels, kernel_size=1
        )

    def forward(self, img: torch.Tensor) -> torch.Tensor:
        enc1: torch.Tensor = self.encoder1(img)
        enc2: torch.Tensor = self.encoder2(self.pool1(enc1))
        enc3: torch.Tensor = self.encoder3(self.pool2(enc2))
        enc4: torch.Tensor = self.encoder4(self.pool3(enc3))

        bottleneck: torch.Tensor = self.bottleneck(self.pool4(enc4))

        upconv4: torch.Tensor = self.upconv4(bottleneck)
        dec4: torch.Tensor = torch.cat((upconv4, enc4), dim=1)
        dec4: torch.Tensor = self.decoder4(dec4)

        upconv3: torch.Tensor = self.upconv3(dec4)
        dec3: torch.Tensor = torch.cat((upconv3, enc3), dim=1)
        dec3: torch.Tensor = self.decoder3(dec3)

        upconv2: torch.Tensor = self.upconv2(dec3)
        dec2: torch.Tensor = torch.cat((upconv2, enc2), dim=1)
        dec2: torch.Tensor = self.decoder2(dec2)

        upconv1: torch.Tensor = self.upconv1(dec2)
        dec1: torch.Tensor = torch.cat((upconv1, enc1), dim=1)
        dec1: torch.Tensor = self.decoder1(dec1)

        conv: torch.Tensor = self.conv(dec1)

        sigmoid: torch.Tensor = torch.sigmoid(conv)

        return sigmoid

    def _block(self, in_channels: int, features: int, padding: int = 1, kernel_size: int = 5, name: str = "block") -> nn.Sequential:
        return nn.Sequential(
            OrderedDict(
                (
                    (
                        f"{name}_conv1",
                        nn.Conv3d(
                            in_channels=in_channels,
                            out_channels=features,
                            kernel_size=kernel_size,
                            padding=padding,
                            bias=True,
                        ),
                    ),
                    (f"{name}_norm1", nn.BatchNorm3d(num_features=features)),
                    (f"{name}_relu1", nn.ReLU(inplace=True)),
                    (
                        f"{name}_conv2",
                        nn.Conv3d(
                            in_channels=features,
                            out_channels=features,
                            kernel_size=kernel_size,
                            padding=padding,
                            bias=True,
                        ),
                    ),
                    (f"{name}_norm2", nn.BatchNorm3d(num_features=features)),
                    (f"{name}_relu2", nn.ReLU(inplace=True)),
                )
            )
        )


def main() -> None:
    import torchviz
    dev: torch.device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
    model: Unet3D = Unet3D()
    model.to(dev)
    model.eval()
    print(next(model.parameters()).is_cuda)  # True
    img: torch.Tensor = torch.randn(1, SIZE, SIZE, SIZE, 1).to(dev)
    out: torch.Tensor = model(img)
    dot: torchviz.Digraph = torchviz.make_dot(out, params=dict(model.named_parameters()), show_attrs=True, show_saved=True)
    dot.render("unet", format="png")
    torch.save(model, "model.pth")
    print(dot)


if __name__ == "__main__":
    main()
