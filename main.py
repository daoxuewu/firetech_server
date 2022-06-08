import configparser
import requests
import socket
from datetime import datetime

# server重啟若時發生 Address already in use 解決方法
# ps -fA | grep python
# kill 81951

# 讀取config.ini檔案
config = configparser.ConfigParser()
config.read('setting.ini',encoding='utf-8')
macids=config.sections()[:] #案場的所有資訊， [:] 代表複製串列

# 設定ip、埠號
clients = []
HOST = '0.0.0.0'
PORT = 8000

# Http回傳訊息
httpHeader = b"""\
HTTP/1.0 200 OK

Hello!
"""

# Line notify推播函式
def lineNotifyMessage(token, msg):

    headers = {
        "Authorization": "Bearer " + token, 
        "Content-Type" : "application/x-www-form-urlencoded"
    }

    payload = {'message': msg }
    r = requests.post("https://notify-api.line.me/api/notify", headers = headers, params = payload)
    return r.status_code

# 替換掉文件中超過七天的舊資料
def alter(file_name):
    '''
    替換掉文件中超過7天的舊資料
    :param file_name:文件名
    :return:
    '''
    file_data=[]
    with open(file_name,'r',encoding='utf-8') as file:
        #print('【存取】')
        # print(file.read())
        for i in file:
            time_format = '%Y-%m-%d %H:%M:%S'
            time_item = i.split(',')[3][:-1]
            temp_str=datetime.strptime(time_item,time_format)
            if (datetime.today()-temp_str).days <= 7:
                file_data.append(i)
    with open(file_name,'w',encoding='utf-8') as file:
        for new_file_data in file_data:
            file.write(new_file_data)   
            #print(new_file_data[:-1])

# 動態顯示煙溫資料的HTTP回應訊息
def feedback_func(Mac,Deg,Smo):
    data =f'''HTTP/1.1 200 OK

裝置識別碼:{Mac}
溫度:{Deg}\u00b0C
煙濃度:{Smo}%
'''
    return data.encode('UTF-8')#encoding 是 utf-8 的話不需要指定 encoding 引數

# 產生http錯誤訊息
def err(socket, code, msg):
    rsp =f'''HTTP/1.0 {code}
    Content-type:text/html
    
    <h1>{code}{msg}</h1>

    '''
    try:
        socket.send(rsp.encode())
    except:
        print('response error!')

# 解析query string
def parse(string):
    arr = string.split('&') 
    args = {}

    for item in arr:
        data = item.split('=')
        args[data[0]] = data[1]
    
    return args

# 處理query string的自訂函式
def query(client, path):
    cmd, string = path.split('?')
    timeString = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if cmd == 'api':
        args = parse(string)
        try:
            Mac = args['M']
            Deg = eval(args['D'])
            Smo = eval(args['S'])
                
            print('【辨識】')
            if Mac in macids:
                print("成功識別裝置!")
            else:
                assert False,'該裝置識別碼未設定'

            if Mac == '':
                print('請指定裝置代碼！', 401, {'ContentType': 'text/html'})
                err(client, "401", 'Mac Error')
            elif  51 > Deg and Deg >= 45:
                print(f'''裝置識別碼:{Mac} 溫度值:{Deg}°C 煙值:{Smo}%''')
                print('溫度過高預警')
                print('【推播】')
                for token in config[Mac]:
                    print('{}, token:{}'.format(token,config[Mac][token]))
                    lineNotifyMessage(config[Mac][token], f'\n溫度過高預警\n溫度值:{Deg}°C,煙值:{Smo}%')
                with open('SMD_log.txt','a+',encoding='utf-8') as file:
                    log_data='裝置識別碼: '+Mac+','+'溫度值: '+str(Deg)+'°C,'+'煙值: '+str(Smo)+'%,'+timeString+'\n'
                    file.write(log_data)
            elif Deg >= 51:
                print(f'''裝置識別碼:{Mac} 溫度值:{Deg}°C 煙值:{Smo}%''')
                print('溫度過高發生火災了!')
                print('【推播】')
                for token in config[Mac]:
                    print('{}, token:{}'.format(token,config[Mac][token]))
                    lineNotifyMessage(config[Mac][token], f'\n溫度過高發生火災了!!\n溫度值:{Deg}°C,煙值:{Smo}%')
                with open('SMD_log.txt','a+',encoding='utf-8') as file:
                    log_data='裝置識別碼: '+Mac+','+'溫度值: '+str(Deg)+'°C,'+'煙值: '+str(Smo)+'%,'+timeString+'\n'
                    file.write(log_data)
            elif Smo >= 14.7:
                print(f'''裝置識別碼:{Mac} 溫度值:{Deg}°C 煙值:{Smo}%''')
                print('煙濃度過高警報!')
                print('【推播】')
                for token in config[Mac]:
                    print('{}, token:{}'.format(token,config[Mac][token]))
                    lineNotifyMessage(config[Mac][token], f'\n煙濃度過高警報!!\n溫度值:{Deg}°C,煙值:{Smo}%')
                with open('SMD_log.txt','a+',encoding='utf-8') as file:
                    log_data='裝置識別碼: '+Mac+','+'溫度值: '+str(Deg)+'°C,'+'煙值: '+str(Smo)+'%,'+timeString+'\n'
                    file.write(log_data)
            else:
                print(f'''裝置識別碼:{Mac} 溫度值:{Deg}°C 煙值:{Smo}%''')

            client.send(feedback_func(Mac,Deg,Smo))
            alter('SMD_log.txt') #更新檔案，超過七天的舊資料移除
        except Exception as e:
            print ("錯誤訊息(e) => ",e,"錯誤訊息(詳細內容) => ",e.args[0]) 
            err(client, "400", "Bad Request")

    else:
        err(client, "404", "Not found")

# 處理用戶端連線請求的自訂函式
def handleRequest(client):
    req = client.recv(1024).decode('utf-8')
    firstLine = req.split('\r\n')[0]
    
    httpMethod = ''
    path = ''

    try:
        httpMethod, path, httpVersion = firstLine.split() 

        print('Method:', httpMethod)
        print('Path:', path)
        print('Version:', httpVersion)

        del httpVersion
    except Exception as e:
        print ("錯誤訊息(e) => ",e,"錯誤訊息(詳細內容) => ",e.args[0]) 
        pass

    if httpMethod == 'GET':
        fileName = path.strip('/')
        print('fileName:',fileName)
        if '?' in fileName:
            query(client, fileName)
        else:
            client.send(httpHeader)
    else:
        err(client, "501", "Not Implemented")

#建立socket連接
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind((HOST, PORT))
s.setblocking(False)
s.listen(5)
print('server start at: %s:%s' % (HOST, PORT))
print('wait for connection...')

#主程式迴圈
while True:
    try:
        client, addr = s.accept()
        client.settimeout(3) 
        print("Client address:", addr)
        print("Connection time is:",datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        clients.append(client)
    except:
        pass 

    for client in clients:
        try:
            handleRequest(client)    
            client.close()
            clients.remove(client)
            print('-----------------------')
        except socket.timeout:  
            print('連線愈時了，關閉正在佔線的連接!')
            client.close()
            clients.remove(client)
            break
        except ConnectionResetError: 
            print('關閉了正在佔線的連接！')
            client.close()
            clients.remove(client)
            break
