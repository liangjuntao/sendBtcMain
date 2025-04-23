# 比特币批量转账工具

这是一个用于批量发送比特币交易的 Python 工具，支持从 Excel 文件读取转账数据，并使用 Native SegWit (P2WPKH) 地址进行批量转账。

## 主要功能

- 支持从 WIF 格式私钥创建 P2WPKH 钱包
- 从 Excel 文件批量读取转账数据
- 自动获取 UTXO 并构建交易
- 支持自定义交易费率
- 自动计算找零
- 交易广播前需要确认
- 详细的日志记录

## 系统要求

- Python 3.6+
- 依赖包：
  - pandas
  - bitcoinlib
  - requests

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置文件

在项目根目录创建 `config.json` 文件，包含以下配置：

```json
{
    "wif_key": "你的WIF格式私钥",
    "excel_path": "转账数据Excel文件路径",
    "fee_rate": "交易费率（satoshi/byte）",
    "min_utxo": "最小UTXO金额（satoshi）"
}
```

## Excel 文件格式

Excel 文件必须包含以下列：
- `address`: 目标比特币地址（必须是 bc1q 开头的 Native SegWit 地址）
- `amount`: 转账金额（以 satoshi 为单位，必须大于 546）

## 使用说明

1. 配置 `config.json` 文件
2. 准备符合格式要求的 Excel 文件
3. 运行程序：
   ```bash
   python send_btc.py
   ```
4. 程序会显示交易详情并请求确认
5. 输入 'Y' 确认广播交易

## 注意事项

- 所有地址必须使用 Native SegWit (bc1q 开头)
- 单笔转账金额必须大于 546 satoshi
- 程序会自动过滤掉金额小于最小 UTXO 要求的输入
- 交易广播前会显示详细信息和请求确认
- 建议在测试网络上先进行测试

## 日志

程序运行时会生成详细的日志，包括：
- 钱包创建信息
- UTXO 获取情况
- 交易构建详情
- 交易广播结果

## 错误处理

程序包含完整的错误处理机制，会在以下情况抛出异常：
- 配置文件格式错误
- Excel 文件格式错误
- 地址格式错误
- 金额格式错误
- UTXO 获取失败
- 交易构建失败
- 交易广播失败 