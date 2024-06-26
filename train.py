import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import models
import torch
from torch import autograd
import torch.nn as nn
from torch.utils.data import DataLoader, dataset
from torchvision.datasets import MNIST
import torchvision.transforms as T
eps = np.finfo(float).eps
import tqdm
from torchsummary import summary
import argparse
import os
import time

desc = "Pytorch implementation of AAE'"
parser = argparse.ArgumentParser(description=desc)
parser.add_argument('--dim_z', type=int, help='Dimensionality of latent variables', default=10)
parser.add_argument('--lr', type=float, default=0.001, help='Learning rate of ADAM optimizer')
parser.add_argument('--epochs', type=int, default=1, help='The number of epochs to run')
parser.add_argument('--batch_size', type=int, default=128, help='Batch size')
parser.add_argument('--use_cuda', type=bool, default=False, help='Use GPU?')
parser.add_argument('--log_interval', type=int, default=100)

args = parser.parse_args()
EPS = 1e-15

use_cuda = True
use_cuda = use_cuda and torch.cuda.is_available()
print(use_cuda)
if use_cuda:
    dtype = torch.cuda.FloatTensor
    device = torch.device("cuda:0")
else:
    dtype = torch.FloatTensor
    device = torch.device("cpu")

Model_dir = 'Models/'
if not os.path.exists(Model_dir):
    os.makedirs(Model_dir)

Data_dir = 'Data/'
if not os.path.exists(Data_dir):
    os.makedirs(Data_dir)

log_dir = 'logs/'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

Fig_dir = 'Figs/'
if not os.path.exists(Fig_dir):
    os.makedirs(Fig_dir)

train_loader = torch.utils.data.DataLoader(MNIST('Data/', train=True, download=True,
                             transform=T.Compose([
                               T.ToTensor(),
                               T.Normalize(
                                 (0.1307,), (0.3081,))
                             ])), batch_size=args.batch_size, shuffle=True)

val_loader = torch.utils.data.DataLoader(MNIST('Data/', train=False, download=True,
                             transform=T.Compose([
                               T.ToTensor(),
                               T.Normalize(
                                 (0.1307,), (0.3081,))
                             ])), batch_size=args.batch_size, shuffle=False)

ae_criterion = nn.MSELoss()

def train_validate(encoder, decoder, Disc, dataloader, optim_encoder, optim_decoder, optim_D, train):
    total_rec_loss = 0
    total_disc_loss = 0
    total_gen_loss = 0
    if train:
        encoder.train()
        decoder.train()
        Disc.train()
    else:
        encoder.eval()
        decoder.eval()
        Disc.eval()

    for i, (data, labels) in enumerate(dataloader):
        for p in Disc.parameters():
            p.requires_grad = False

        real_data_v = autograd.Variable(data).to(device)
        real_data_v = real_data_v.view(-1, 784)
        encoding = encoder(real_data_v)
        fake = decoder(encoding)
        ae_loss = ae_criterion(fake, real_data_v)
        total_rec_loss += ae_loss.item()
        if train:
            optim_encoder.zero_grad()
            optim_decoder.zero_grad()
            ae_loss.backward()
            optim_encoder.step()
            optim_decoder.step()

        encoder.eval()
        z_real_gauss = autograd.Variable(torch.randn(data.size()[0], args.dim_z) * 5.).to(device)
        D_real_gauss = Disc(z_real_gauss)

        z_fake_gauss = encoder(real_data_v)
        D_fake_gauss = Disc(z_fake_gauss)

        D_loss = -torch.mean(torch.log(D_real_gauss + EPS) + torch.log(1 - D_fake_gauss + EPS))
        total_disc_loss += D_loss.item()

        if train:
            optim_D.zero_grad()
            D_loss.backward()
            optim_D.step()

        if train:
            encoder.train()
        else:
            encoder.eval()
        z_fake_gauss = encoder(real_data_v)
        D_fake_gauss = Disc(z_fake_gauss)

        G_loss = -torch.mean(torch.log(D_fake_gauss + EPS))
        total_gen_loss += G_loss.item()

        if train:
            optim_encoder_reg.zero_grad()
            G_loss.backward()
            optim_encoder_reg.step()

        if i % 100 == 0:
            print('\n Step [%d], recon_loss: %.4f, discriminator_loss :%.4f , generator_loss:%.4f' % (i, ae_loss.item(), D_loss.item(), G_loss.item()))

    M = len(dataloader.dataset)
    return total_rec_loss / M, total_disc_loss / M, total_gen_loss / M

encoder = models.Encoder(784, args.dim_z).to(device)
decoder = models.Decoder(784, args.dim_z).to(device)
Disc = models.Discriminator(args.dim_z, 500).to(device)

optim_encoder = torch.optim.Adam(encoder.parameters(), lr=args.lr)
optim_decoder = torch.optim.Adam(decoder.parameters(), lr=args.lr)
optim_D = torch.optim.Adam(Disc.parameters(), lr=args.lr)
optim_encoder_reg = torch.optim.Adam(encoder.parameters(), lr=0.0001)

schedulerDisc = torch.optim.lr_scheduler.ExponentialLR(optim_D, gamma=0.99)
schedulerD = torch.optim.lr_scheduler.ExponentialLR(optim_decoder, gamma=0.99)
schedulerE = torch.optim.lr_scheduler.ExponentialLR(optim_encoder, gamma=0.99)

train_loss = []
val_loss = []
for epoch in range(args.epochs):
    l1, l2, l3 = train_validate(encoder, decoder, Disc, train_loader, optim_encoder, optim_decoder, optim_D, True)
    print('\n epoch:{} ---- training loss:{}'.format(epoch, l1))
    train_loss.append(l1)

    if epoch % 5 == 0:
        l1, l2, l3 = train_validate(encoder, decoder, Disc, val_loader, optim_encoder, optim_decoder, optim_D, False)
        print('\n epoch:{} ---- validation loss loss:{}'.format(epoch, l1))
        val_loss.append(l1)

sns.set()
plt.rcParams['figure.figsize'] = 5, 5
plt.plot(np.arange(len(train_loss)), train_loss, label='train')
plt.plot(np.arange(0, len(val_loss) * 5, 5), val_loss, label='val')
plt.title('Training')
plt.xlabel('Step')
plt.ylabel('Reconstruction loss')
plt.legend()
plt.grid(True)
plt.savefig(Fig_dir + 'training_' + str(args.epochs) + 'epochs.png')

torch.save(encoder.state_dict(), Model_dir + f'encoder_z{args.dim_z}_epch{args.epochs}.pt')
torch.save(decoder.state_dict(), Model_dir + f'decoder_z{args.dim_z}_epch{args.epochs}.pt')
torch.save(Disc.state_dict(), Model_dir + f'disc_z{args.dim_z}_epch{args.epochs}.pt')



