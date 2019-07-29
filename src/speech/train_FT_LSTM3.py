import torch
from torch import optim
from model_FT_LSTM3 import CNN_FTLSTM
from process_FT_LSTM import IEMOCAP, my_collate
from torch.utils.data import DataLoader
from torch.optim.lr_scheduler import ReduceLROnPlateau, CosineAnnealingLR, MultiStepLR
import pdb
from torch.nn import DataParallel
import pickle
import numpy as np
from torch.nn.utils.rnn import pad_sequence, pack_padded_sequence
import argparse
from sklearn.metrics import confusion_matrix

def init_parser():
    parser = argparse.ArgumentParser(description='Train and test your model as specified by the parameters you enter')
    parser.add_argument('--batch_size', '-b', default=128, type=int, dest='batch_size')
    parser.add_argument('--out_channels_1', '-out1', default=64, type=int, dest='out_channels1')
    parser.add_argument('--out_channels_2', '-out2', default=16, type=int, dest='out_channels2')
    parser.add_argument('--kernel_size_cnn_1', '-kc1', default=4, type=int, dest='kernel_size_cnn1')
    parser.add_argument('--kernel_size_cnn_2','-kc2',default=2,type=int,dest='kernel_size_cnn2')
    parser.add_argument('--stride_size_cnn_1', '-sc1', default=1, type=int, dest='stride_size_cnn1')
    parser.add_argument('--stride_size_cnn_2', '-sc2', default=1, type=int, dest='stride_size_cnn2')
    parser.add_argument('--kernel_size_pool_1', '-kp1', default=2, type=int, dest='kernel_size_pool1')
    parser.add_argument('--kernel_size_pool_2','-kp2',default=2,type=int,dest='kernel_size_pool2')
    parser.add_argument('--stride_size_pool', '-sp', default=2, type=int, dest='stride_size_pool')
    parser.add_argument('--weight', '-w', default=0.5, type=float, dest='weight')
    parser.add_argument('--special', '-special', default="concat", type=str, dest='special')
    parser.add_argument('--file','-f',default="recent2",type=str,dest='file_path')
    return parser.parse_args()

def train_model(args):
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    device_ids=[0,1,2,3]
    num_devices=len(device_ids)
    batch_size=args.batch_size
    input_channels = 1
    out_channels = [args.out_channels1, args.out_channels2]
    kernel_size_cnn = [[args.kernel_size_cnn1, args.kernel_size_cnn2],[args.kernel_size_cnn2, args.kernel_size_cnn1]]
    stride_size_cnn = [[args.stride_size_cnn1, args.stride_size_cnn2],[args.stride_size_cnn2, args.stride_size_cnn1]]
    kernel_size_pool = [[args.kernel_size_pool1, args.kernel_size_pool2],[args.kernel_size_pool2, args.kernel_size_pool1]]
    stride_size_pool = [args.stride_size_pool]*2
    hidden_dim=200
    num_layers_ftlstm=2
    hidden_dim_lstm=200
    epoch_num=50
    nfft=[512,1024]
    weight = args.weight
    # Load the training data
    training_data = IEMOCAP(name='mel', nfft=nfft, train=True)
    train_loader = DataLoader(dataset=training_data, batch_size=batch_size, shuffle=True, collate_fn=my_collate, num_workers=0, drop_last=True)
    testing_data = IEMOCAP(name='mel', nfft=nfft, train=False)
    test_loader = DataLoader(dataset=testing_data, batch_size=batch_size, shuffle=True, collate_fn=my_collate, num_workers=0,drop_last=False)
    model = CNN_FTLSTM(input_channels, out_channels, kernel_size_cnn,
                    stride_size_cnn, kernel_size_pool, stride_size_pool,nfft,
                    hidden_dim,num_layers_ftlstm,weight,args.special,device)

    print("============================ Number of parameters ====================================")
    print(str(sum(p.numel() for p in model.parameters() if p.requires_grad)))


    path="batch_size:{};out_channels:{};kernel_size_cnn:{};stride_size_cnn:{};kernel_size_pool:{};stride_size_pool:{};weight:{};special:{}".format(args.batch_size,out_channels,kernel_size_cnn,stride_size_cnn,kernel_size_pool,stride_size_pool, weight,args.special)
    file_path="/scratch/speech/models/classification/FT_LSTM_"+args.file_path+".txt"
    with open(file_path,"a+") as f:
        f.write("\n"+"============ model starts ===========")
        f.write("\n"+"model_parameters: "+str(sum(p.numel() for p in model.parameters() if p.requires_grad))+"\n"+path+"\n")
    model.cuda()
    model=DataParallel(model,device_ids=device_ids)
    model.train()
    ## optimizer
    # Use Adam as the optimizer with learning rate 0.01 to make it fast for testing purposes
    optimizer = optim.Adam(model.parameters(),lr=0.001)
    optimizer2=optim.SGD(model.parameters(), lr=0.1)
    scheduler = ReduceLROnPlateau(optimizer=optimizer,factor=0.5, patience=2, threshold=1e-3)
    #scheduler2=ReduceLROnPlateau(optimizer=optimizer2, factor=0.5, patience=2, threshold=1e-3)
    #scheduler2 =CosineAnnealingLR(optimizer2, T_max=300, eta_min=0.0001)
    scheduler3 =MultiStepLR(optimizer, [10,15,20,25],gamma=0.5)

    print("=================")
    print(len(training_data))
    print(len(testing_data))
    print("===================")

    test_acc=[]
    train_acc=[]
    test_loss=[]
    train_loss=[]
    class_acc= []
    print("Model Initialized: {}".format(path)+"\n")
    for epoch in range(epoch_num):  # again, normally you would NOT do 300 epochs, it is toy data
        print("===================================" + str(epoch+1) + "==============================================")
        losses = 0
        correct=0
        model.train()
        for j, (input_lstm, input1, input2, target, seq_length) in enumerate(train_loader):
            #if (j+1)%20==0:
                #print("=================================Train Batch"+ str(j+1)+str(weight)+"===================================================")
            num=input_lstm.shape[0]
            if num%num_devices!=0:
                input_lstm=input_lstm[:int(num-num%num_devices)]
                input1=input1[:int(num-num%num_devices)]
                input2=input2[:int(num-num%num_devices)]
                target=target[:int(num-num%num_devices)]
                seq_length=seq_length[:int(num-num%num_devices)]
            model.zero_grad()
            losses_batch,correct_batch= model(input_lstm, input1, input2, target, seq_length)
            loss = torch.mean(losses_batch,dim=0)
            correct_batch=torch.sum(correct_batch,dim=0)
            losses += loss.item() * (int(num-num%num_devices))
            loss.backward()
            weight=model.module.state_dict()["weight"]
            optimizer.step()
            correct += correct_batch.item()
        accuracy=correct*1.0/(j*batch_size+int(num-num%num_devices))
        losses=losses / (j*batch_size+int(num-num%num_devices))
        losses_test = 0
        correct_test = 0
        class_accuracy_test = 0
        output = []
        y_true = []
        y_pred = []
        torch.save(model.module.state_dict(), "/scratch/speech/models/classification/FT_LSTM_"+path+"_epoch_{}.pt".format(epoch+1))
        model.eval()
        with torch.no_grad():
            for j,(input_lstm, input1, input2, target, seq_length) in enumerate(test_loader):
                #if (j+1)%10==0: print("=================================Test Batch"+ str(j+1)+ "===================================================")
                num=input_lstm.shape[0]
                if num%num_devices!=0:
                    input_lstm=input_lstm[:int(num-num%num_devices)]
                    input1=input1[:int(num-num%num_devices)]
                    input2=input2[:int(num-num%num_devices)]
                    target=target[:int(num-num%num_devices)]
                    seq_length=seq_length[:int(num-num%num_devices)]
                losses_batch,correct_batch,(target_index, pred_index)= model(input_lstm,input1, input2, target, seq_length,train=False)
                output.append((target_index, pred_index))
                loss = torch.mean(losses_batch,dim=0)
                correct_batch=torch.sum(correct_batch,dim=0)
                losses_test += loss.item() * (int(num-num%num_devices))
                correct_test += correct_batch.item()
        for target_index, pred_index in output:
            y_true = y_true + target_index.tolist()
            y_pred = y_pred + pred_index.tolist()
            cm = confusion_matrix(y_true, y_pred)
            cm_normalized = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
        print("how many correct:", correct_test)
        print("confusion matrix: ")
        with np.printoptions(precision=4, suppress=True):
            print(cm_normalized)
        accuracy_test = correct_test * 1.0 / (j*batch_size+int(num-num%num_devices))
        losses_test = losses_test / (j*batch_size+int(num-num%num_devices))
        for i in range(4):
            class_accuracy_test += cm_normalized[i,i]*0.25
        # data gathering
        test_acc.append(accuracy_test)
        train_acc.append(accuracy)
        test_loss.append(losses_test)
        train_loss.append(losses)
        class_acc.append(class_accuracy_test)

        print("Epoch: {}-----------Training Loss: {:06.5f} -------- Testing Loss: {:06.5f} -------- Training Acc: {:06.5f} -------- Testing Acc: {:06.5f} -------- Class Acc: {:06.5f}".format(epoch+1,losses,losses_test, accuracy, accuracy_test, class_accuracy_test)+"\n")
        with open(file_path,"a+") as f:
            f.write("Epoch: {}-----------Training Loss: {:06.5f} -------- Testing Loss: {:06.5f} -------- Training Acc: {:06.5f} -------- Testing Acc: {:06.5f} -------- Class Acc: {:06.5f}".format(epoch+1,losses,losses_test, accuracy, accuracy_test, class_accuracy_test)+"\n")
            f.write("confusion_matrix:"+"\n")
            np.savetxt(f,cm_normalized,delimiter=' ',fmt="%6.5f")
            if epoch==epoch_num-1:
                f.write("Best Accuracy:{:06.5f}".format(max(test_acc))+"\n")
                f.write("Average Top 10 Accuracy:{:06.5f}".format(np.mean(np.sort(np.array(test_acc))[-10:]))+"\n")
                f.write("Best Class Accuracy:{:06.5f}".format(max(class_acc))+"\n")
                f.write("Average Top 10 Class Accuracy:{:06.5f}".format(np.mean(np.sort(np.array(class_acc))[-10:]))+"\n")
                f.write("/scratch/speech/models/classification/FT_LSTM"+path+"_epoch_{}.pt".format(epoch+1)+"\n")
                f.write("/scratch/speech/models/classification/FT_LSTM_checkpoint_stats"+path+".pkl"+"\n")
                f.write("============================= model ends ==================================="+"\n")
    pickle_out=open("/scratch/speech/models/classification/FT_LSTM_checkpoint_stats"+path+".pkl","wb")
    pickle.dump({"test_acc":test_acc, "class_acc": class_acc, "train_acc": train_acc, "train_loss": train_loss,"test_loss":test_loss},pickle_out)
    pickle_out.close()
    print(file_path)
    print()

if __name__ == '__main__':
    args = init_parser()
    train_model(args)