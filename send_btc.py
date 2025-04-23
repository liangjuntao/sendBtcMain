import pandas as pd
from bitcoinlib.wallets import Wallet
from bitcoinlib.transactions import Transaction
from bitcoinlib.keys import HDKey, Key
from bitcoinlib.encoding import pubkeyhash_to_addr_bech32, hash160, to_bytes, to_hexstring
import logging
import os
from bitcoinlib.services.services import Service
import requests
import json
import time
from bitcoinlib.scripts import Script

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config():
    """
    从配置文件加载配置
    :return: 配置字典
    """
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {str(e)}")
        raise

def create_wallet_from_wif(wif_key):
    """
    从WIF格式的私钥直接生成P2WPKH地址
    :param wif_key: WIF格式的私钥
    :return: Key对象和地址
    """
    try:
        # 验证WIF私钥格式
        if not wif_key.startswith(('K', 'L', '5')):
            raise ValueError("无效的WIF私钥格式，应以K、L或5开头")
            
        try:
            # 直接使用WIF私钥创建Key对象
            key = Key(wif_key, network='bitcoin')
            
            # 获取公钥
            public_key = key.public_hex
            
            # 计算公钥的hash160
            pubkey_hash = hash160(bytes.fromhex(public_key))
            
            # 生成bech32地址
            address = pubkeyhash_to_addr_bech32(pubkey_hash, prefix='bc')
            
            if not address.startswith('bc1q'):
                raise ValueError("生成的地址不是P2WPKH地址")
                
            logger.info(f"WIF私钥验证成功")
            logger.info(f"生成的P2WPKH地址: {address}")
            return key, address
            
        except Exception as e:
            logger.error(f"私钥处理失败: {str(e)}")
            raise
            
    except Exception as e:
        logger.error(f"钱包操作失败: {str(e)}")
        raise

def read_excel_data(file_path):
    """
    从Excel文件读取转账数据
    :param file_path: Excel文件路径
    :return: DataFrame对象
    """
    try:
        df = pd.read_excel(file_path)
        # 验证必要的列是否存在
        if 'address' not in df.columns or 'amount' not in df.columns:
            raise ValueError("Excel文件必须包含 'address' 和 'amount' 列")
        
        # 验证地址格式和金额
        for idx, row in df.iterrows():
            # 验证地址格式
            address = str(row['address']).strip()
            if not address.startswith('bc1q'):
                raise ValueError(f"第{idx+1}行的地址不是Native SegWit地址: {address}")
            
            # 验证金额（确保是整数且大于0）
            try:
                amount = int(row['amount'])
                if amount <= 0:
                    raise ValueError(f"第{idx+1}行的金额必须大于0: {amount}")
                if amount < 546:  # 比特币网络的最小输出金额
                    raise ValueError(f"第{idx+1}行的金额小于最小输出金额(546 satoshi): {amount}")
            except ValueError as e:
                raise ValueError(f"第{idx+1}行的金额格式错误: {str(e)}")
            except Exception as e:
                raise ValueError(f"第{idx+1}行的金额处理失败: {str(e)}")
        
        # 确保amount列是整数类型
        df['amount'] = df['amount'].astype(int)
        if df['amount'].isna().any():
            raise ValueError("amount列包含无效的数值")
            
        logger.info(f"成功验证 {len(df)} 条转账记录")
        return df
    except Exception as e:
        logger.error(f"读取Excel文件失败: {str(e)}")
        raise

def get_utxos_from_api(address, min_utxo=1000):
    """
    从API获取UTXO
    :param address: 比特币地址
    :param min_utxo: 最小UTXO金额（satoshi）
    :return: UTXO列表
    """
    url = f"https://mempool.space/api/address/{address}/utxo"
    logger.info(f"正在从API获取UTXO: {url}")
    response = requests.get(url)
    if response.status_code == 200:
        utxos = response.json()
        # 过滤掉金额小于min_utxo的UTXO
        filtered_utxos = [utxo for utxo in utxos if utxo['value'] >= min_utxo]
        logger.info(f"找到 {len(utxos)} 个UTXO，其中 {len(filtered_utxos)} 个满足最小金额要求")
        
        # 打印每个UTXO的详细信息
        for i, utxo in enumerate(filtered_utxos):
            logger.info(f"UTXO {i}:")
            logger.info(f"  txid: {utxo['txid']}")
            logger.info(f"  vout: {utxo['vout']}")
            logger.info(f"  value: {utxo['value']}")
            logger.info(f"  status: {utxo.get('status', 'unknown')}")
            
        return filtered_utxos
    else:
        raise ValueError(f"获取UTXO失败，状态码: {response.status_code}")

def send_batch_transaction(key, records, fee_rate, min_utxo=1000):
    """
    发送批量交易
    :param key: Key对象
    :param records: 转账记录列表
    :param fee_rate: 费率（satoshi/byte）
    :param min_utxo: 最小UTXO金额（satoshi）
    :return: 交易ID
    """
    try:
        # 获取钱包地址
        from bitcoinlib.encoding import pubkeyhash_to_addr_bech32, hash160
        public_key = key.public_hex
        pubkey_hash = hash160(bytes.fromhex(public_key))
        wallet_address = pubkeyhash_to_addr_bech32(pubkey_hash, prefix='bc')
        
        if not wallet_address.startswith('bc1q'):
            raise ValueError("钱包地址必须是P2WPKH地址")
            
        # 获取UTXO
        utxos = get_utxos_from_api(wallet_address, min_utxo)
        if not utxos:
            raise ValueError(f"没有可用的UTXO（最小金额要求: {min_utxo} satoshi）")
            
        # 创建交易
        t = Transaction(witness_type='segwit', network='bitcoin')
        
        # 添加输入
        total_input = 0
        for utxo in utxos:
            # 验证UTXO数据
            if not isinstance(utxo['vout'], int):
                raise ValueError(f"UTXO的vout必须是整数: {utxo['vout']}")
                
            # 添加输入并设置金额、地址和脚本类型
            t.add_input(
                utxo['txid'], 
                utxo['vout'], 
                value=utxo['value'], 
                address=wallet_address,
                script_type='p2wpkh'
            )
            total_input += utxo['value']
            
        # 添加输出
        total_output = 0
        for record in records:
            amount = int(record['amount'])
            address = record['address']
            
            if not address.startswith('bc1q'):
                raise ValueError(f"目标地址必须是P2WPKH地址: {address}")
                
            t.add_output(amount, address)
            total_output += amount
            
        # 计算交易大小和手续费
        tx_size = len(t.raw_hex()) // 2
        fee = int(tx_size * fee_rate)
        
        # 添加找零输出
        change = total_input - total_output - fee
        if change > 0:
            t.add_output(change, wallet_address)
            
        # 签名交易
        for i, utxo in enumerate(utxos):
            t.sign(key, i, hash_type='SIGHASH_ALL')
        
        # 验证签名
        if not t.verify():
            raise ValueError("交易签名验证失败")
            
        # 获取原始交易数据
        tx_hex = t.raw_hex()
        
        # 打印交易信息
        logger.info("\n交易信息:")
        logger.info(f"输入金额: {total_input} satoshi")
        logger.info(f"输出金额: {total_output} satoshi")
        logger.info(f"手续费: {fee} satoshi")
        logger.info(f"找零金额: {change} satoshi")
        logger.info(f"原始交易数据: {tx_hex}")
        
        # 确认广播
        confirm = input("\n是否广播交易？(Y/N): ")
        if confirm.upper() != 'Y':
            logger.info("交易已取消")
            return None
            
        # 广播交易
        response = requests.post(
            'https://mempool.space/api/tx',
            data=tx_hex,
            headers={'Content-Type': 'text/plain'}
        )
        
        if response.status_code == 200:
            txid = response.text
            logger.info(f"交易广播成功，交易ID: {txid}")
            return txid
        else:
            raise ValueError(f"交易广播失败: {response.text}")
            
    except Exception as e:
        logger.error(f"发送交易失败: {str(e)}")
        raise

def main():
    try:
        # 加载配置
        config = load_config()
        wif_key = config['wif_key']
        excel_path = config['excel_path']
        fee_rate = float(config['fee_rate'])
        min_utxo = int(config['min_utxo'])
        
        logger.info("配置加载成功")
        
        # 创建钱包
        key, wallet_address = create_wallet_from_wif(wif_key)
        logger.info("钱包创建成功")
        
        # 读取转账数据
        df = read_excel_data(excel_path)
        logger.info(f"成功读取 {len(df)} 条转账记录")
        
        # 准备转账数据
        recipients = []
        for _, row in df.iterrows():
            try:
                address = str(row['address']).strip()
                amount_satoshi = int(row['amount'])
                if amount_satoshi <= 0:
                    raise ValueError(f"金额必须大于0: {amount_satoshi}")
                recipients.append({'address': address, 'amount': amount_satoshi})
                logger.info(f"处理记录: 地址={address}, 金额={amount_satoshi} satoshi")
            except Exception as e:
                logger.error(f"处理记录失败: {str(e)}, 行数据={row}")
                raise
        
        # 发送交易
        txid = send_batch_transaction(key, recipients, fee_rate, min_utxo)
        logger.info(f"交易发送成功，交易ID: {txid}")
        
    except Exception as e:
        logger.error(f"程序执行失败: {str(e)}")
        raise

if __name__ == "__main__":
    main() 