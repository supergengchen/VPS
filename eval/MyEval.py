import glob
import os
import cv2
import argparse
from tqdm import tqdm
import prettytable as pt
import numpy as np

import torch

import metrics as Measure


def get_competitors(root):
    for model_name in os.listdir(root):
        print('\'{}\''.format(model_name), end=', ')


def evaluator(gt_pth_lst, pred_pth_lst):
    # define measures
    FM = Measure.Fmeasure()
    WFM = Measure.WeightedFmeasure()
    SM = Measure.Smeasure()
    EM = Measure.Emeasure()
    MAE = Measure.MAE()
    POLYP = Measure.POLYP(len(gt_pth_lst))

    assert len(gt_pth_lst) == len(pred_pth_lst)

    # evaluator
    with torch.no_grad():
        # calculate metric value
        for idx in tqdm(range(len(gt_pth_lst))):
            gt_pth = gt_pth_lst[idx]
            pred_pth = pred_pth_lst[idx]
            assert os.path.isfile(gt_pth) and os.path.isfile(pred_pth)
            pred_ary = cv2.imread(pred_pth, cv2.IMREAD_GRAYSCALE)
            gt_ary = cv2.imread(gt_pth, cv2.IMREAD_GRAYSCALE)
            # ensure the shape of prediction is matched to gt
            if not gt_ary.shape == pred_ary.shape:
                # print(gt_ary.shape, pred_ary.shape)
                pred_ary = cv2.resize(pred_ary, (gt_ary.shape[1], gt_ary.shape[0]))

            FM.step(pred=pred_ary, gt=gt_ary)
            WFM.step(pred=pred_ary, gt=gt_ary)
            SM.step(pred=pred_ary, gt=gt_ary)
            EM.step(pred=pred_ary, gt=gt_ary)
            MAE.step(pred=pred_ary, gt=gt_ary)
            # TODO: 为什么这里需要idx？
            POLYP.step(pred=pred_ary, gt=gt_ary, idx=idx)

        fm = FM.get_results()['fm']
        wfm = WFM.get_results()['wfm']
        sm = SM.get_results()['sm']
        em = EM.get_results()['em']
        mae = MAE.get_results()['mae']
        polyp_res = POLYP.get_results()
        Sen = polyp_res['Sen']
        Spe = polyp_res['Spe']
        Dic = polyp_res['Dic']
        IoU = polyp_res['IoU']

    return fm, wfm, sm, em, mae, Sen, Spe, Dic, IoU


# TODO: 我理解这一段函数可以不需要？你有什么其他用途？
def eval_all(opt, txt_save_path):
    # evaluation for whole dataset
    for _data_name in opt.data_lst:
        print('#' * 20, _data_name, '#' * 20)
        filename = os.path.join(txt_save_path, '{}_eval.txt'.format(_data_name))
        with open(filename, 'w+') as file_to_write:
            tb = pt.PrettyTable()
            tb.field_names = ["Dataset", "Method", "Smeasure", "wFmeasure", "MAE", "adpEm", "meanEm", "maxEm", "adpFm",
                              "meanFm", "maxFm"]
            for _model_name in opt.model_lst:
                gt_src = os.path.join(opt.gt_root, _data_name, 'GT')
                pred_src = os.path.join(opt.pred_root, _model_name, _data_name, 'Frame')

                # get the valid filename list
                img_name_lst = os.listdir(gt_src)

                fm, wfm, sm, em, mae = evaluator(
                    gt_pth_lst=[os.path.join(gt_src, i) for i in img_name_lst],
                    pred_pth_lst=[os.path.join(pred_src, i) for i in img_name_lst]
                )
                tb.add_row([_data_name, _model_name, sm.round(3), wfm.round(3), mae.round(3), em['adp'].round(3),
                            em['curve'].mean().round(3), em['curve'].max().round(3), fm['adp'].round(3),
                            fm['curve'].mean().round(3), fm['curve'].max().round(3)])
            print(tb)
            file_to_write.write(str(tb))
            file_to_write.close()


# TODO: 以sequence为粒度eval
def eval_engine_vps(opt, txt_save_path):
    # evaluation for whole dataset
    for _data_name in opt.data_lst:
        print('#' * 20, 'Current Dataset:', _data_name, '#' * 20)
        filename = os.path.join(txt_save_path, '{}_eval.txt'.format(_data_name))
        with open(filename, 'w+') as file_to_write:
            # initial settings for PrettyTable
            tb = pt.PrettyTable()
            tb.field_names = [
                "Dataset", "Method", 
                "Smeasure", "wFmeasure", "MAE", 
                "adpEm", "meanEm", "maxEm", 
                "adpFm", "meanFm", "maxFm",
                "meanSen", "maxSen", 
                "meanSpe", "maxSpe", 
                "meanDic", "maxDic",
                "meanIoU", "maxIoU"]
            # iter each method for current dataset
            for _model_name in opt.model_lst:
                print('#' * 10, 'Current Method:', _model_name, '#' * 10)
                gt_src = os.path.join(opt.gt_root, _data_name, 'GT')
                pred_src = os.path.join(opt.pred_root, _model_name, _data_name)
                # get the sequence list for current dataset
                case_list = os.listdir(gt_src)
                case_score_list = []
                # iter each video frame for current method-dataset
                for case in case_list:
                    case_gt_name_list = glob.glob(gt_src + '/{}/*.png'.format(case))
                    try:
                        case_gt_name_list.sort(
                            key=lambda name: (int(name.split('/')[-2]), int(name.split('/')[-1].rstrip('.png')))
                        )
                    except:
                        case_gt_name_list.sort(
                            key=lambda name: (int(name.split("/")[-2].split('case')[1].split('_')[0]),
                                              0 if not len(name.split('/')[-2].split('_')) > 1 else int(
                                                  name.split('/')[-2].split('_')[1]),
                                              int(name.split('/')[-1].split('_a')[1].split('_')[0]),
                                              int(name.split('/')[-1].split('_image')[1].split('.png')[
                                                      0])))
                    # for fair comparison, we remove the first frame and last frame in the video
                    # TODO: reference: xxx 
                    case_gt_name_list = case_gt_name_list[1:-1]
                    case_pred_name_list = [gt.replace(gt_src, pred_src) for gt in case_gt_name_list]

                    fm, wfm, sm, em, mae, Sen, Spe, Dic, IoU = evaluator(
                        gt_pth_lst=case_gt_name_list,
                        pred_pth_lst=case_pred_name_list
                    )
                    # TODO: 这里提前使用round会不会让精度降低？
                    # calculate all the metrics at frame-level
                    case_score_list.append([
                        [sm.round(3)]*256, [wfm.round(3)]*256, [mae.round(3)]*256, 
                        [em['adp'].round(3)]*256, em['curve'], 
                        [fm['adp'].round(3)]*256, fm['curve'],
                        Sen, Spe, Dic, IoU])
                # calculate all the metrics at sequence-level
                case_score_list = np.mean(np.array(case_score_list), axis=0)
                case_score_list = [
                    case_score_list[0].mean().round(3), case_score_list[1].mean().round(3), case_score_list[2].mean().round(3),
                    case_score_list[3].mean().round(3), case_score_list[4].mean().round(3), case_score_list[4].max().round(3),
                    case_score_list[5].mean().round(3), case_score_list[6].mean().round(3), case_score_list[6].max().round(3),
                    case_score_list[7].mean().round(3), case_score_list[7].max().round(3),
                    case_score_list[8].mean().round(3), case_score_list[8].max().round(3),
                    case_score_list[9].mean().round(3), case_score_list[9].max().round(3),
                    case_score_list[10].mean().round(3), case_score_list[10].max().round(3)]
                tb.add_row([_data_name, _model_name] + list(case_score_list))
            print(tb)
            file_to_write.write(str(tb))
            file_to_write.close()


if __name__ == '__main__':
    # TODO: 是否可以考虑把所有的潜在对象（例如：default=['2021-ICCV-FSNet','2021-NIPS-STCN', '2021-NIPS-UniTrack']）放入choice参数中
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--gt_root', type=str, help='custom your ground-truth root',
        # default='C:/Users/v-ychou/Dataset/_Dataset/')
        default='data/GT/')
    parser.add_argument(
        '--pred_root', type=str, help='custom your prediction root',
        # default='C:/Users/v-ychou/Dataset/_Dataset/Benchmark/')
        default='data/Pred/')
    parser.add_argument(
        '--data_lst', type=list, help='set the dataset what you wanna to test',
        # default=['CVC-ClinicDB-612', "TestHardDataset"],
        default=['CVC-ColonDB-300'])
    parser.add_argument(
        '--model_lst', type=list, help='candidate competitors',
        # default=['2015-MICCAI-UNet', '2018-TMI-UNet++', '2020-MICCAI-ACSNet', '2020-MICCAI-PraNet',
        #          '2021-MICCAI-SANet', '2021-TPAMI-SINetV2'],
        # default=['2019-CVPR-STM', '2019-TPAMI-COSNet', '2020-TPAMI-CFBI', '2020-CVPR-Trans',],
        # default=['2021-ICCV-FSNet','2021-NIPS-STCN', '2021-NIPS-UniTrack'],
        default=['2019-TPAMI-COSNet'],
        choices=[])
    parser.add_argument(
        '--txt_name', type=str, help='logging root',
        default='2019-TPAMI-COSNet')
    parser.add_argument(
        '--check_integrity', type=bool, help='whether to check the file integrity',
        default=True)
    opt = parser.parse_args()

    txt_save_path = './eval-result/{}/'.format(opt.txt_name)
    os.makedirs(txt_save_path, exist_ok=True)

    # check the integrity of each candidates
    if opt.check_integrity:
        for _data_name in opt.data_lst:
            for _model_name in opt.model_lst:
                gt_pth = os.path.join(opt.gt_root, _data_name, 'GT')
                pred_pth = os.path.join(opt.pred_root, _model_name, _data_name)
                if not sorted(os.listdir(gt_pth)) == sorted(os.listdir(pred_pth)):
                    print(len(sorted(os.listdir(gt_pth))), len(sorted(os.listdir(pred_pth))))
                    print('The {} Dataset of {} Model is not matching to the ground-truth'.format(_data_name, _model_name))
    else:
        print('>>> Skip check the integrity of each candidates ...')
    
    # start eval engine
    eval_engine_vps(opt, txt_save_path)