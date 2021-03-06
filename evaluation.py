import os
import argparse

import numpy as np
from net_sg import PlusLatent
from product_data import design_dy
from timeit import time

import torch
import torch.nn as nn

from torchvision import datasets, models, transforms
from torch.autograd import Variable
import torch.backends.cudnn as cudnn
import torch.optim.lr_scheduler

parser = argparse.ArgumentParser(description='Deep Hashing evaluate mAP')
parser.add_argument('--pretrained', type=str, default=50, metavar='pretrained_model',
                    help='loading pretrained model(default = None)')
parser.add_argument('--bits', type=int, default=48, metavar='bts',
                    help='binary bits')
# parser.add_argument('--path', type=str, default='model_loss_tanh/48/0.5cr/0.1', metavar='P',help='path directory')
parser.add_argument('--path', type=str, default='model_dy/48/0.01', metavar='P',help='path directory')
parser.add_argument('--class_num', type=int, default=14, help="class number")    ##   14   10
args = parser.parse_args()

# def load_data():
#     transform_train = transforms.Compose(
#         [transforms.Resize(224),
#           transforms.ToTensor(),
#           transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010))])
#     transform_test = transforms.Compose(
#         [transforms.Resize(224),
#           transforms.ToTensor(),
#           transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010))])
#     trainset = datasets.CIFAR10(root='./data', train=True, download=True,
#                                 transform=transform_train)
#     trainloader = torch.utils.data.DataLoader(trainset, batch_size=20,
#                                               shuffle=False, num_workers=0)

#     testset = datasets.CIFAR10(root='./data', train=False, download=True,
#                                 transform=transform_test)
#     testloader = torch.utils.data.DataLoader(testset, batch_size=20,
#                                               shuffle=False, num_workers=0)
#     return trainloader, testloader

def load_data():
    transform_train = transforms.Compose(
          [transforms.Resize(256),
            transforms.RandomCrop(224),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010))])
    transform_test = transforms.Compose(
          [transforms.Resize(224),
            transforms.ToTensor(),
            transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010))])
    
    train_data = design_dy(root='./data', train=True, transform=transform_train)
    test_data = design_dy(root='./data', train=False, transform=transform_test)
    
    trainloader = torch.utils.data.DataLoader(train_data, batch_size=20, shuffle=True, num_workers=0, pin_memory=True)
    
    testloader = torch.utils.data.DataLoader(test_data, batch_size=20, shuffle=False, num_workers=0, pin_memory=True)
    
    return trainloader, testloader


def binary_output(dataloader):
    net = PlusLatent(args.bits,args.class_num)
    net.load_state_dict(torch.load('./{}/{}'.format(args.path, args.pretrained)))
    use_cuda = torch.cuda.is_available()
    if use_cuda:
        net.cuda()
        
    full_batch_output = torch.cuda.FloatTensor()
    full_batch_label = torch.cuda.LongTensor()
    net.eval()
    
    with torch.no_grad():
        for batch_idx, (inputs, targets) in enumerate(dataloader):
            print (batch_idx)
            if use_cuda:
                inputs, targets = inputs.cuda(), targets.cuda()
            inputs, targets = Variable(inputs), Variable(targets)
            outputs, _ = net(inputs)
            print (outputs)
            full_batch_output = torch.cat((full_batch_output, outputs.data), 0)
            full_batch_label = torch.cat((full_batch_label, targets.data), 0)
            print (torch.sign(full_batch_output))
        return torch.sign(full_batch_output), full_batch_label    ###  round

def precision(trn_binary, trn_label, tst_binary, tst_label):
    trn_binary = trn_binary.cpu().numpy()
    trn_binary = np.asarray(trn_binary, np.int32)
    trn_label = trn_label.cpu().numpy()
    tst_binary = tst_binary.cpu().numpy()
    tst_binary = np.asarray(tst_binary, np.int32)
    tst_label = tst_label.cpu().numpy()
    classes = np.max(tst_label) + 1
    for i in range(classes):
        if i == 0:
            tst_sample_binary = tst_binary[np.random.RandomState(seed=i).permutation(np.where(tst_label==i)[0])[:100]]
            tst_sample_label = np.array([i]).repeat(100)
            continue
        else:
            tst_sample_binary = np.concatenate([tst_sample_binary, tst_binary[np.random.RandomState(seed=i).permutation(np.where(tst_label==i)[0])[:100]]])
            tst_sample_label = np.concatenate([tst_sample_label, np.array([i]).repeat(100)])
    query_times = tst_sample_binary.shape[0]
    trainset_len = trn_binary.shape[0]
    AP = np.zeros(query_times)
    precision_radius = np.zeros(query_times)
    Ns = np.arange(1, trainset_len + 1)
    sum_tp = np.zeros(trainset_len)
    
    for i in range(query_times):
        print('Query ', i+1)
        query_label = tst_sample_label[i]
        query_binary = tst_sample_binary[i,:]
        query_result = np.count_nonzero(query_binary != trn_binary, axis=1)    #don't need to divide binary length
        # print(query_result.shape)
        
        sort_indices = np.argsort(query_result)
        buffer_yes = np.equal(query_label, trn_label[sort_indices]).astype(int)
        
        P = np.cumsum(buffer_yes) / Ns
        print(np.max(query_result))
        # print(np.where(np.sort(query_result)>0)[0].shape)
        
        precision_radius[i] = P[np.where(np.sort(query_result)>2)[0][0]-1]
        
        AP[i] = np.sum(P * buffer_yes) /sum(buffer_yes)
        sum_tp = sum_tp + np.cumsum(buffer_yes)
        
    precision_at_k = sum_tp / Ns / query_times
    recall_at_k = sum_tp / (trainset_len/classes) /query_times
    
    index = [100, 200,300, 400,500, 600,700, 800,900, 1000,1100, 1200,1300, 1400,1500, 1600]
    # index = [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000]
    
    index = [i - 1 for i in index]
    print('precision at k:', precision_at_k[index])
    print('recall at k:', recall_at_k[index])
    np.save(args.path+'/precision_at_k', precision_at_k)
    np.save(args.path+'/recall_at_k', recall_at_k)
    
    print('precision within Hamming radius 2:', np.mean(precision_radius))
    map = np.mean(AP)
    print('mAP:', map)



if os.path.exists('./result/train_binary') and os.path.exists('./result/train_label') and \
    os.path.exists('./result/test_binary') and os.path.exists('./result/test_label') and args.pretrained == 0:
    train_binary = torch.load('./result/train_binary')
    train_label = torch.load('./result/train_label')
    test_binary = torch.load('./result/test_binary')
    test_label = torch.load('./result/test_label')

else:
    trainloader, testloader = load_data()
    train_binary, train_label = binary_output(trainloader)
    test_binary, test_label = binary_output(testloader)
    if not os.path.isdir('result'):
        os.mkdir('result')
    torch.save(train_binary, './result/train_binary')
    torch.save(train_label, './result/train_label')
    torch.save(test_binary, './result/test_binary')
    torch.save(test_label, './result/test_label')
    
# train_binary = torch.load('./result/train_binary')
# train_label = torch.load('./result/train_label')
# test_binary = torch.load('./result/test_binary')
# test_label = torch.load('./result/test_label')


precision(train_binary, train_label, test_binary, test_label)
