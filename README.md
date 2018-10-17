# walle-python
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://raw.githubusercontent.com/Meituan-Dianping/walle/master/LICENSE)

<a href="https://github.com/Meituan-Dianping/walle" target="_blank">walle渠道打包工具</a>的 python版本
<br><u>（只有**读取和修改**渠道信息功能，不包含签名功能）</u>
### Note ###
目前只支持python3
### Usage ###
```
python main.py -i xxx
```
支持参数列表通过 -h查看
```
python main.py -h
```

具体用例

- 查看walle渠道信息   

  ```python main.py -i xxx.apk -v```

- 查看签名区域的所有信息   

  ```python main.py -i xxx.apk -r```

- 修改apk的渠道信息（必须是V2Scheme签名的apk）  

    ```python main.py -i xxx/xxx.apk -c xxx/channel.json -o xxx/xxx/```   

   其中 ```-i``` 参数可以是目录，也可以是单个apk的路径     
   ```-o``` 是输出的apk路径，如果指明，默认是生成到apk目录的channels文件夹下
   
- 清除apk渠道信息（必须是V2Scheme签名的apk）  

    ```python main.py -i xxx/xxx.apk -e```    

   需要注意的是，这里是直接修改源apk

- 扫描检测目录中的所有apk文件   

    ```python main.py -i xxx/xxx -d```  

  (这个可以配合上述几个功能一起使用，如果是有多个apk要处理的话)