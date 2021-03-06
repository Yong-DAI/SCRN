import numpy as np
import torch
import torch.nn as nn
from torch.autograd import Variable
from util.distance import distance

def hashing_loss(output, label, class_num, alpha):
    """
    https://github.com/weixu000/DSH-pytorch/blob/master/main.py
    compute hashing loss
    b are output, cls are targets
    automatically consider all n^2 pairs
    """
    b, cls, m = output, label, class_num
    y = (cls.unsqueeze(0) != cls.unsqueeze(1)).float().view(-1)
    dist = ((b.unsqueeze(0) - b.unsqueeze(1)) ** 2).sum(dim=2).view(-1)
    loss = (1 - y) / 2 * dist + y / 2 * (m - dist).clamp(min=0)

    loss = loss.mean() + alpha * (b.abs() - 1).abs().sum(dim=1).mean() * 2

    return loss


def pairwise_loss(output, label, alpha=1.0, class_num=1.0, l_threshold=15.0):
    '''https://github.com/thuml/HashNet/issues/27#issuecomment-494265209'''
    bits = output.shape[1]
    similarity = Variable(torch.mm(label.data.float(), label.data.float().t()) > 0).float()
    dot_product = alpha * torch.mm(output, output.t()) / bits
    
    mask_dot = dot_product.data > l_threshold
    mask_exp = dot_product.data <= l_threshold
    mask_positive = similarity.data > 0
    mask_negative = similarity.data <= 0
    mask_dp = mask_dot & mask_positive
    mask_dn = mask_dot & mask_negative
    mask_ep = mask_exp & mask_positive
    mask_en = mask_exp & mask_negative

    dot_loss = dot_product * (1-similarity)
    exp_loss = torch.log(1+torch.exp(dot_product)) - similarity * dot_product
    
    loss = (torch.sum(torch.masked_select(exp_loss, Variable(mask_ep))) + torch.sum(torch.masked_select(dot_loss, Variable(mask_dp)))) * class_num + \
            torch.sum(torch.masked_select(exp_loss, Variable(mask_en))) + torch.sum(torch.masked_select(dot_loss, Variable(mask_dn)))

    return loss / (torch.sum(mask_positive.float()) * class_num + torch.sum(mask_negative.float()))


def pairwise_loss_exam(output, label, alpha=1.0, class_num=1.0, l_threshold=15.0):
    '''https://github.com/thuml/HashNet/issues/27#issuecomment-494265209'''

    similarity = Variable(torch.mm(label.data.float(), label.data.float().t()) > 0).float()
    dot_product = alpha * torch.mm(output, output.t())
    
    mask_dot = dot_product.data > l_threshold
    mask_exp = dot_product.data <= l_threshold
    
    mask_positive = similarity.data > 0
    mask_negative = similarity.data <= 0
    
    mask_dp = mask_dot & mask_positive
    mask_dn = mask_dot & mask_negative
    mask_ep = mask_exp & mask_positive
    mask_en = mask_exp & mask_negative

    dot_loss = dot_product * (1-similarity)
    exp_loss = torch.log(1+torch.exp(dot_product)) - similarity * dot_product
    loss = (torch.sum(torch.masked_select(exp_loss, Variable(mask_ep))) + torch.sum(torch.masked_select(dot_loss, Variable(mask_dp)))) * class_num + \
            torch.sum(torch.masked_select(exp_loss, Variable(mask_en))) + torch.sum(torch.masked_select(dot_loss, Variable(mask_dn)))

    return loss / (torch.sum(mask_positive.float()) * class_num + torch.sum(mask_negative.float()))

def pairwise_loss_weight(outputs,label):
    
    similarity = Variable(torch.mm(label.data.float(), label.data.float().t()) > 0).float()
    dot_product = torch.mm(outputs, outputs.t())
    #exp_product = torch.exp(dot_product)

    mask_positive = similarity.data > 0
    mask_negative = similarity.data <= 0
    exp_loss = torch.log(1+torch.exp(-torch.abs(dot_product))) + torch.max(dot_product, Variable(torch.FloatTensor([0.]).cuda()))-similarity * dot_product
    #weight
    S1 = torch.sum(mask_positive.float())
    S0 = torch.sum(mask_negative.float())
    S = S0+S1
    exp_loss[similarity.data > 0] = exp_loss[similarity.data > 0] * (S / S1)
    exp_loss[similarity.data <= 0] = exp_loss[similarity.data <= 0] * (S / S0)

    loss = torch.sum(exp_loss) / S

    #exp_loss = torch.sum(torch.log(1 + exp_product) - similarity * dot_product)

    return loss

def pairwise_loss_debug(output, label, alpha=5.0):
    '''https://github.com/thuml/HashNet/issues/17#issuecomment-443137529'''
    bits = output.shape[1]
    similarity = Variable(torch.mm(label.data.float(), label.data.float().t()) > 0).float()
    dot_product = alpha * torch.mm(output, output.t()) / bits
    
    mask_positive = similarity.data > 0
    mask_negative = similarity.data <= 0
    #weight
    S1 = torch.sum(mask_positive.float())
    S0 = torch.sum(mask_negative.float())
    S = S0 + S1
    
    exp_loss = torch.log(1+torch.exp(dot_product)) - similarity * dot_product
    exp_loss[similarity.data > 0] = exp_loss[similarity.data > 0] * (S / S1)
    exp_loss[similarity.data <= 0] = exp_loss[similarity.data <= 0] * (S / S0)
    loss = torch.sum(exp_loss) / S
    return loss


def contrastive_loss(output, label, margin=24):
    '''contrastive loss
    - Deep Supervised Hashing for Fast Image Retrieval
    '''
    batch_size = output.shape[0]
    S =  torch.mm(label.float(), label.float().t())
    dist = distance(output)
    loss_1 = S * dist + (1 - S) * torch.max(margin - dist, torch.zeros_like(dist))
    loss = torch.sum(loss_1) / (batch_size*(batch_size-1))
    return loss


def exp_loss(output, label, alpha, balanced=False):
    '''exponential loss
    '''
    batch_size, bit = output.shape
    mask = (torch.eye(batch_size) == 0).to(torch.device("cuda"))

    S =  torch.mm(label.float(), label.float().t())
    S_m = torch.masked_select(S, mask)

    # sigmoid
    D = distance(output, dist_type='cosine')
    E = torch.log(1 + torch.exp(-alpha * (1-2*D)))
    E_m = torch.masked_select(E, mask)
    loss_1 = 10 * S_m * E_m + (1 - S_m) * (E_m - torch.log((torch.exp(E_m) - 1).clamp(1e-6)))

    if balanced:
        S_all = batch_size * (batch_size - 1)
        S_1 = torch.sum(S)
        balance_param = (S_all / S_1) * S + (1 - S)
        B_m= torch.masked_select(balance_param, mask)
        loss_1 = B_m * loss_1

    loss = torch.mean(loss_1)
    return loss


def quantization_loss(output):
    loss = torch.mean((torch.abs(output) - 1) ** 2)
    return loss

def correlation_loss(output):
    loss = (output @ torch.ones(output.shape[1], 1)).sum()
    
    return loss