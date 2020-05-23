from _util import add_gimpenv_to_pythonpath, tqdm_as_gimp_progress

add_gimpenv_to_pythonpath()

from gimpfu import *
import PIL.Image as pil
import torch
import torch.hub
from torchvision import transforms
import numpy as np
import matplotlib as mpl
import matplotlib.cm as cm


@tqdm_as_gimp_progress("Downloading model")
def load_model(device):
    repo = "valgur/monodepth2"
    pretrained_model = "mono+stereo_640x192"
    encoder = torch.hub.load(repo, "ResnetEncoder", pretrained_model, map_location=device)
    depth_decoder = torch.hub.load(repo, "DepthDecoder", pretrained_model, map_location=device)
    encoder.to(device)
    depth_decoder.to(device)
    return depth_decoder, encoder


@torch.no_grad()
def getMonoDepth(input_image):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # LOADING PRETRAINED MODEL
    depth_decoder, encoder = load_model(device)

    input_image = pil.fromarray(input_image)
    original_width, original_height = input_image.size
    input_image = input_image.resize((encoder.feed_width, encoder.feed_height), pil.LANCZOS)
    input_image = transforms.ToTensor()(input_image).unsqueeze(0)
    input_image = input_image.to(device)

    # PREDICTION
    features = encoder(input_image)
    outputs = depth_decoder(features)

    disp = outputs[("disp", 0)]
    disp_resized = torch.nn.functional.interpolate(
        disp, (original_height, original_width), mode="bilinear", align_corners=False)

    # Convert to colormapped depth image
    disp_resized_np = disp_resized.squeeze().cpu().numpy()
    vmax = np.percentile(disp_resized_np, 95)
    normalizer = mpl.colors.Normalize(vmin=disp_resized_np.min(), vmax=vmax)
    mapper = cm.ScalarMappable(norm=normalizer, cmap='magma')
    colormapped_im = (mapper.to_rgba(disp_resized_np)[:, :, :3] * 255).astype(np.uint8)
    return colormapped_im


def channelData(layer):  # convert gimp image to numpy
    region = layer.get_pixel_rgn(0, 0, layer.width, layer.height)
    pixChars = region[:, :]  # Take whole layer
    bpp = region.bpp
    # return np.frombuffer(pixChars,dtype=np.uint8).reshape(len(pixChars)/bpp,bpp)
    return np.frombuffer(pixChars, dtype=np.uint8).reshape(layer.height, layer.width, bpp)


def createResultLayer(image, name, result):
    rlBytes = np.uint8(result).tobytes()
    rl = gimp.Layer(image, name, image.width, image.height, image.active_layer.type, 100, NORMAL_MODE)
    region = rl.get_pixel_rgn(0, 0, rl.width, rl.height, True)
    region[:, :] = rlBytes
    image.add_layer(rl, 0)
    gimp.displays_flush()


def MonoDepth(img, layer):
    gimp.progress_init("Generating disparity map for " + layer.name + "...")

    imgmat = channelData(layer)
    cpy = getMonoDepth(imgmat)

    createResultLayer(img, 'new_output', cpy)


register(
    "MonoDepth",
    "MonoDepth",
    "Generate monocular disparity map based on deep learning.",
    "Kritik Soman",
    "Your",
    "2020",
    "MonoDepth...",
    "*",  # Alternately use RGB, RGB*, GRAY*, INDEXED etc.
    [(PF_IMAGE, "image", "Input image", None),
     (PF_DRAWABLE, "drawable", "Input drawable", None),
     ],
    [],
    MonoDepth, menu="<Image>/Layer/GIML-ML")

main()
