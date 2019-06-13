import torch
import pickle
from torch.utils.data import Dataset, DataLoader


class IEMOCAP(Dataset):
    def __init__(self):
        pickle_in = open('/scratch/speech/IEMOCAP_dictionary_5.pkl', 'rb')
        data = pickle.load(pickle_in)
        self.seq_length = data["seq_length"]
        self.input = data["input"]
        self.target = data["target"]

    def __len__(self):
        return len(self.input)

    def __getitem__(self, index):
        sample = {'input': torch.from_numpy(self.input[index]),
                  'target': torch.from_numpy(self.target[index]),
                  'seq_length': torch.from_numpy(self.seq_length[index])}
        return sample


def my_collate(batch):
    input = [item for item in batch['input']]
    target = [item for item in batch['target']]
    seq_length = [item for item in batch['seq_length']]
    target = torch.LongTensor(target)
    seq_length = torch.LongTensor(seq_length)
    return [input, target, seq_length]


dataset = IEMOCAP()
train_loader = DataLoader(dataset=dataset, batch_size=128, shuffle=True, collate_fn=my_collate, num_workers=0)
for i, sample in enumerate(train_loader):
    if i < 3:
        print(sample)
