from flask import Flask, render_template
from datetime import datetime
import time
import requests
import configparser
import os
import hashlib

import xml.etree.ElementTree as ET

# 引用 APSchedule
from flask_apscheduler import APScheduler 

app = Flask(__name__)

#定時任務配置
class Config(object):
    JOBS = [
        {
            'id': 'job1',# Job 的唯一ID
            'func': 'ser:aps_test', # Job 執行的function
            # 'args': (1, 2), # 如果function需要参数，就在这里添加
            # 'trigger': 'interval',
            # 'seconds': 3
            'trigger': {
                'type': 'interval', # 類型
                # 'day_of_week': "0-6", # 可定義具體哪幾天要執行
                # 'hour': '*',  # 小時數
                # 'minutes': 1,    # 每間隔一分鐘執行一次
                'hours': 1,        # 每間個一小時執行一次
            }
        }
    ]
    #APS(調度器)的API的開關
    SCHEDULER_API_ENABLED = True 

# test
def aps_test():
    per_hr_wirte_log()
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '已自動儲存一筆資料')

# 每小時存一次資料到per_hr_log.txt
def per_hr_wirte_log():
    # 從檔案載入並解析 XML 資料
    tree = ET.parse('cs6000_xml_rtn.xml')
    root = tree.getroot()    

    alter_old_data('per_hr_log.txt',1) #更新檔案，超過一天的舊資料移除
    # 讀到幾個裝置的初始值
    device_index = 0 
    # 只從第一層子節點中搜尋，傳回所有找到的節點
    for country in root.findall('device'):
        # 只從第一層子節點中搜尋，傳回第一個找到的節點
        mac = country.find('mac').text
        id = country.find('id').text
        timestamp = country.find('timestamp').text
        state = country.find('state').text
        temperature = country.find('temperature').text # 只有廠商類型為「全部分享」時才顯示temperature、smoke資訊。
        smoke = country.find('smoke').text
        
        timeString = timestamp_to_strtime(timestamp) # 因為java裡預設是13位（milliseconds，毫秒級的），python是10位(秒級的)，所以收到的資料這邊要做一個轉換

        device_index += 1 #裝置編號，每執行一次迴圈就加一
        print(f'*****device{device_index}*****','\nmac:',mac ,'\nid:', id, '\ntimestamp', timeString, '\nstate', state, '\ntemperature', temperature ,'\nsmoke', smoke)

        print('【辨識】')
        if mac not in macids:
            print(f'未設定裝置識別碼:{mac}')
            return f'裝置識別碼(mac):{mac} 未設定'
        else:
            print(f"成功識別裝置!")

        #寫進檔案per_hr_log中 
        with open('per_hr_log.txt','a+',encoding='utf-8') as file: # a+ 打開一個文件用於讀寫。如果該文件已存在，文件指針將會放在文件的结尾。文件打開時會是追加模式。如果該文件不存在，創建新文件用於讀寫。
            log_data=mac+','+temperature+','+smoke+','+f'graph_{mac},'+timeString+'\n' # add backslash n for the newline characters at the end of each line
            file.write(log_data)
                


# Line notify推播函式
def lineNotifyMessage(token, msg):

    headers = {
        "Authorization": "Bearer " + token, 
        "Content-Type" : "application/x-www-form-urlencoded"
    }

    payload = {'message': msg }
    r = requests.post("https://notify-api.line.me/api/notify", headers = headers, params = payload)
    return r.status_code


# 讀取cs6000後台資訊設定檔
cs6000_api_config = configparser.ConfigParser()
cs6000_api_config.read('cs6000_api_setting.ini',encoding='utf-8')

hashKey = cs6000_api_config.get('CS6000後台設定','HashKey')# 頂石雲端提供的hashKey
XML_API_URL = cs6000_api_config.get('CS6000後台設定','XML_API_URL') # 頂石雲端提供的XML API URL

# 讀取line notify token 和 macid 設定檔
notify_config = configparser.ConfigParser()
notify_config.read('notify_setting.ini',encoding='utf-8')
macids=notify_config.sections()[:] #案場的所有資訊， [:] 代表複製串列

def req_url(XML_API_URL,timeString,random_num,data_sha):
    """
    返回請求 cs6000 server 之回傳值

    :params XML_API_URL: cs6000後台廠商設定XML網址
    :params data_sha: 加密後的資料
    :params timestamp: 時間戳
    :params random_num: 隨機數
    """
    headers = {
        "Content-Type" : "application/x-www-form-urlencoded"
    }
    payload = {
        "timestamp": timeString,
        "random": random_num,
        "key": data_sha
    } 

    r = requests.post(XML_API_URL, headers = headers, params = payload)
    return r.text

# 替換掉文件中超過n天的舊資料 (舊資料留7天，還要寫一個判斷24小時內的function來顯示Line chart的數據)
def alter_old_data(file_name,days):
    '''
    替換掉文件中超過 days 天的舊資料\n
    :param file_name:文件名\n
    :parm days:天數(超過這個天數的資料會被覆蓋掉)\n
    :return:
    '''
    file_data=[]
    with open(file_name,'r',encoding='utf-8') as file:
        #print('【存取】')
        # print(file.read())
        for line in file:
            time_format = '%Y-%m-%d %H:%M:%S'
            time_item = line.split(',')[4][:-1]# s[:-1] 等價於 s[0:len(s)]，資料全拿除了最後一個元素(換行符號\n)
            temp_str=datetime.strptime(time_item,time_format)
            if (datetime.today()-temp_str).days < days:
                file_data.append(line)
    with open(file_name,'w',encoding='utf-8') as file:
        for new_file_data in file_data:
            file.write(new_file_data)   
            #print(new_file_data[:-1])

def timestamp_to_strtime(timestamp):
    """將13位整數的毫秒時間戳轉化成本地時間(字符串格式)
    :parm timestamp: 13位整數的毫秒時間戳 (1658278708057)
    :return: 返回字符串格式 {str}'2022-07-20 09:02:53'
    """
    local_str_time = datetime.fromtimestamp(int(timestamp) / 1000).strftime("%Y-%m-%d %H:%M:%S")
    return local_str_time

# 去CS6000的後台撈資料丟到檔案cs6000_xml_rtn.xml中
def write_xml_rtn_to_file():
    timeString = int(time.time()) #印出時間戳，並取整數 
    random_num = os.urandom(6).hex() #隨機生成亂數

    before_data = f'hashKey={hashKey}&timestamp={timeString}&random={random_num}&hashKey={hashKey}'
    # print("金鑰生成前的資料:",before_data)
    data_sha = hashlib.sha256(before_data.encode('utf-8')).hexdigest().upper() #sha256並轉大寫
    # print("生成的金鑰:",data_sha)
    print('----------------------------')
    xml_rtn = req_url(XML_API_URL,timeString,random_num,data_sha)
    print("原始回傳值:\n",xml_rtn)#原本讀到的值
    # 將資料寫入record6000.xml中
    with open("cs6000_xml_rtn.xml",'w',encoding='utf-8') as record_file:
        record_file.write(xml_rtn) 


# server首頁
@app.route("/")
def index():
    write_xml_rtn_to_file() #把xml返回值寫進檔案cs6000_xml_rtn.xml
    print('----------------------------')

    # 從檔案載入並解析 XML 資料
    tree = ET.parse('cs6000_xml_rtn.xml')
    root = tree.getroot()    

    # 首頁table的標題
    homepage_headings = ("device",'mac','id','timestamp','state','temperature','smoke','24hr line chart')
    # 顯示在首頁table中的資料
    all_record_data = [] 
    # 讀到幾個裝置的初始值
    device_index = 0 
    # 只從第一層子節點中搜尋，傳回所有找到的節點
    for country in root.findall('device'):
        # 只從第一層子節點中搜尋，傳回第一個找到的節點
        mac = country.find('mac').text
        id = country.find('id').text
        timestamp = country.find('timestamp').text
        state = country.find('state').text
        temperature = country.find('temperature').text # 只有廠商類型為「全部分享」時才顯示temperature、smoke資訊。
        smoke = country.find('smoke').text
        
        timeString = timestamp_to_strtime(timestamp) # 因為java裡預設是13位（milliseconds，毫秒級的），python是10位(秒級的)，所以收到的資料這邊要做一個轉換

        device_index += 1 #裝置編號，每執行一次迴圈就加一
        print(f'*****device{device_index}*****','\nmac:',mac ,'\nid:', id, '\ntimestamp', timeString, '\nstate', state, '\ntemperature', temperature ,'\nsmoke', smoke)
        all_record_data.extend([(str(device_index),mac,id,timeString,state,temperature,smoke,f'graph_{mac}')])#加str是為了在html中可以被jinja2語法去迭代

        print('【辨識】')
        if mac not in macids:
            print(f'未設定裝置識別碼:{mac}')
            return f'裝置識別碼(mac):{mac} 未設定'
        else:
            print(f"成功識別裝置!")

        #若火警，將資料寫入alert_log.txt、並且進行linenoitfy推播
        if state == "Alarm":
            for token in notify_config[mac]:
                print('{}, token:{}'.format(token,notify_config[mac][token]))
                lineNotifyMessage(notify_config[mac][token], f'\n案場警報!!\n裝置:{mac}\n溫度值:{temperature}°C,煙值:{smoke}%')
            with open('alert_log.txt','a+',encoding='utf-8') as file: # a+ 打開一個文件用於讀寫。如果該文件已存在，文件指針將會放在文件的结尾。文件打開時會是追加模式。如果該文件不存在，創建新文件用於讀寫。
                log_data='狀態: '+state+','+'裝置識別碼: '+mac+','+'溫度值: '+temperature+'°C,'+'煙值: '+smoke+'%,'+timeString+'\n' # add backslash n for the newline characters at the end of each line
                file.write(log_data)
        elif state == "Warning": #若預警，將資料寫入alert_log.txt、並且進行linenoitfy推播
            for token in notify_config[mac]:
                print('{}, token:{}'.format(token,notify_config[mac][token]))
                lineNotifyMessage(notify_config[mac][token], f'\n案場預警!!\n裝置:{mac}\n溫度值:{temperature}°C,煙值:{smoke}%')
            with open('alert_log.txt','a+',encoding='utf-8') as file: # a+ 打開一個文件用於讀寫。如果該文件已存在，文件指針將會放在文件的结尾。文件打開時會是追加模式。如果該文件不存在，創建新文件用於讀寫。
                log_data='狀態: '+state+','+'裝置識別碼: '+mac+','+'溫度值: '+temperature+'°C,'+'煙值: '+smoke+'%,'+timeString+'\n' # add backslash n for the newline characters at the end of each line
                file.write(log_data)
        elif state == "Normal":
            print(f'''案場狀態正常,裝置識別碼:{mac} 溫度值:{temperature}°C 煙值:{smoke}%''')
        else:
            print(f'案場狀態異常，接收到的狀態為:{state}')
            return f'案場狀態異常，接收到的狀態為:{state}'

    return render_template("index.html", homepage_headings=homepage_headings, all_python_record_data=all_record_data )


# 24hr溫度計錄圖表
@app.route("/<graph_link_index>/") 
def graph(graph_link_index):
    Mac ='' # 該裝置的mac address
    graph_data = []# 用來傳遞給網頁的資料list
    with open('per_hr_log.txt','r',encoding='utf-8') as file:
        for line in file:         
            device_mac,temperature,smoke,graph_num,timeString=line.split(',')     
            if graph_link_index == graph_num: #如果graph_link_index等於per_hr_log.txt中該圖表的名稱，就將資料取出     
                graph_data.extend([(timeString[5:-4],temperature,smoke)]) #timeString是為了調整時間格式，所以加slice切片
                Mac = device_mac
            else:
                pass
    
    # print('graph_data========================',graph_data)
    labels = [row[0] for row in graph_data]
    temperature_values = [row[1] for row in graph_data]
    smoke_values = [row[2] for row in graph_data]
    
    # data = [
    #     ("7/19 01:00",15,3),
    #     ("7/19 02:00",14,1),
    #     ("7/19 03:00",19,2),
    #     ("7/19 04:00",8,1),
    #     ("7/19 05:00",7,0),
    #     ("7/19 06:00",4,3),
    #     ("7/19 07:00",26,1),
    #     ("7/19 08:00",18,2),
    #     ("7/19 09:00",33,4),
    #     ("7/19 10:00",15,3),
    #     ("7/19 11:00",20,1),
    #     ("7/19 12:00",9,2),
    #     ("7/19 13:00",15,3),
    #     ("7/19 14:00",14,1),
    #     ("7/19 15:00",19,2),
    #     ("7/19 16:00",8,1),
    #     ("7/19 17:00",7,0),
    #     ("7/19 18:00",4,3),
    #     ("7/19 19:00",26,1),
    #     ("7/19 20:00",18,2),
    #     ("7/19 21:00",33,4),
    #     ("7/19 22:00",15,3),
    #     ("7/19 23:00",20,1),
    #     ("7/19 24:00",9,2),
    # ]


    # labels = [row[0] for row in data]
    # temperature_values = [row[1] for row in data]
    # smoke_values = [row[2] for row in data]
    
    templateData = {
    'mac_address' :Mac,
    'labels' : labels,
    'temperature_values' : temperature_values,
    'smoke_values'  : smoke_values,
    }        

    return render_template("graph.html",**templateData)



# 煙溫警報歷史紀錄
@app.route("/alert_history") 
def alert_history():
    alter_old_data('alert_log.txt',7) #更新檔案，超過七天的舊資料移除

    # 顯示在煙溫歷史紀錄頁面table中的資料
    alert_history_data = [] 

    # 歷史紀錄 table的 標題
    alert_history_page_headings = ["狀態",'mac','溫度','煙值','API最後更新時間']

    with open('alert_log.txt','r',encoding='utf-8') as file:
        for line in file:         
            state,mac,temperature,smoke,alert_time=line.split(',')       
            alert_history_data.extend([(state,mac,temperature,smoke,alert_time)])

    return render_template('alert_history.html',alert_history_page_headings=alert_history_page_headings,python_alert_history_data=alert_history_data)

if __name__ == "__main__":
    # 定時任務，導入配置
    app.config.from_object(Config())

    # 進行flask-apscheduler的初始化，定時任務
    scheduler = APScheduler()
    scheduler.init_app(app)
    scheduler.start()

    # app.run(debug=True,host='localhost',port=8080) # localhost:8080
    # app.run(debug=True,port=8080) # 網址: 127.0.0.1:8080
    # app.run(host='0.0.0.0') # 網址: 192.168.1.94
    app.run()