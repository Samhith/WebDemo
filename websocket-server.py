#!/usr/bin/env python2
#
# Copyright 2015-2016 Carnegie Mellon University
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import shutil
import time
import pickle
import datetime
fileDir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(fileDir, "..", ".."))

import txaio
txaio.use_twisted()

from autobahn.twisted.websocket import WebSocketServerProtocol, \
    WebSocketServerFactory
from twisted.internet import task, defer
from twisted.internet.ssl import DefaultOpenSSLContextFactory

from twisted.python import log

import pandas as pd
import argparse
import cv2
import imagehash
import json
from PIL import Image
import numpy as np
import os
import StringIO
import urllib
import base64

from sklearn.decomposition import PCA
from sklearn.grid_search import GridSearchCV
from sklearn.manifold import TSNE
from sklearn.svm import SVC

import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.cm as cm

import openface

nameCounter = 0
modelDir = os.path.join(fileDir, 'models')
dlibModelDir = os.path.join(modelDir, 'dlib')
openfaceModelDir = os.path.join(modelDir, 'openface')
# For TLS connections
tls_crt = os.path.join(fileDir, 'tls', 'server.crt')
tls_key = os.path.join(fileDir, 'tls', 'server.key')

parser = argparse.ArgumentParser()
parser.add_argument('--dlibFacePredictor', type=str, help="Path to dlib's face predictor.",
                    default=os.path.join(dlibModelDir, "shape_predictor_68_face_landmarks.dat"))
parser.add_argument('--networkModel', type=str, help="Path to Torch network model.",
                    default=os.path.join(openfaceModelDir, 'nn4.small2.v1.t7'))
parser.add_argument('--imgDim', type=int,
                    help="Default image dimension.", default=96)
parser.add_argument('--cuda', action='store_true')
parser.add_argument('--unknown', type=bool, default=False,
                    help='Try to predict unknown people')
parser.add_argument('--port', type=int, default=9000,
                    help='WebSocket Port')

args = parser.parse_args()

align = openface.AlignDlib(args.dlibFacePredictor)
net = openface.TorchNeuralNet(args.networkModel, imgDim=args.imgDim,
                              cuda=args.cuda)
model_location = 'model.sav'


class Face:

    def __init__(self, rep, identity):
        self.rep = rep
        self.identity = identity

    def __repr__(self):
        return "{{id: {}, rep[0:5]: {}}}".format(
            str(self.identity),
            self.rep[0:5]
        )


class OpenFaceServerProtocol(WebSocketServerProtocol):
    def __init__(self):
        super(OpenFaceServerProtocol, self).__init__()
        self.images = {}
        self.training = True
        self.testing = False
        self.people = []
        self.svm = None
        self.frameNum = 0
        self.clientIP = ""
        self.dirname = ""
        self.UName = ""
        self.MailID = ""
        self.uniqueID = ""
        self.mobileNo = ""
        self.org = ""
        self.details = None
        self.prediction = -1
        
        if args.unknown:
            self.unknownImgs = np.load("./examples/web/unknown.npy")

    def onConnect(self, request):
        print("Client connecting: {0}".format(request.peer))
        self.clientIP = str(request.peer)
        self.training = True
        tempPath = "./"+self.clientIP
        self.dirname = tempPath

    def onOpen(self):
        print("WebSocket connection open.")

    def onMessage(self, payload, isBinary):
        self.frameNum = self.frameNum + 1
        print("Received paylod number : "+str(self.frameNum))
        raw = payload.decode('utf8')
        msg = json.loads(raw)
        print("Received {} message of length {}.".format(
            msg['type'], len(raw)))

        if msg['type'] == "TRAINING":
            self.training = msg['val']
            if not self.training:
                self.trainSVM()
        elif msg['type'] == "TRAINALLIMAGES":
            print("Calling training all images")
            self.TrainAllImages()


        elif msg['type'] == "INFO":
            print("Name of the person is : ")
            print(msg['name'])
            self.UName = msg['name']
            print("Mail of the person is : ")
            print(msg['mail'])
            self.MailID = msg['mail']
            self.mobileNo = msg['mobile']
            self.org = msg['company']
            print(self.mobileNo)
            print(self.org)
            self.sendMessage('{"type": "END_FACE_COLLECTION"}')
        elif msg['type'] == "TESTING":
            print("Trying to detect face")
            self.testing = True
            self.processFrame_testing(msg['dataURL'])
            self.sendMessage('{"type": "PROCESSED" }')
            #Load SVM
            #self.svm = loaded SVM

        elif msg['type'] == "STOPPED_ACK":
            print("Storing Faces-------------------------------------")
            self.storefaces()
            print(self.uniqueID)
            self.sendMessage('{"type": "STORED_PAGE2", "id": ' + self.uniqueID + '}')
        elif msg['type'] == "FEEDBACK":
            print("Taking feedback")
            self.processFeedback(msg['value'], msg['actualID'])


        elif msg['type'] == "NULL":
            tok = 1
            self.sendMessage('{"type": "NULL"}')

        elif msg['type'] == "FRAME":
            print("received frame")
            self.processFrame(msg['dataURL'], msg['identity'], msg['ID'])
            self.sendMessage('{"type": "PROCESSED"}')

        elif msg['type'] == "register_click":
            print(msg['val'])

        elif msg['type'] == "UPDATE_IDENTITY":
            h = msg['hash'].encode('ascii', 'ignore')
            if h in self.images:
                self.images[h].identity = msg['idx']
                if not self.training:
                    self.trainSVM()
            else:
                print("Image not found.")

        elif msg['type'] == "REMOVE_IMAGE":
            h = msg['hash'].encode('ascii', 'ignore')
            if h in self.images:
                del self.images[h]
                if not self.training:
                    self.trainSVM()
            else:
                print("Image not found.")

        elif msg['type'] == 'REQ_TSNE':
            self.sendTSNE(msg['people'])
        else:           
            print("Warning: Unknown message type: {}".format(msg['type']))

    def storefaces(self):
        
        #Generating Unique Id to user
        ts = time.time()
        self.uniqueID = datetime.datetime.fromtimestamp(ts).strftime('%Y%m%d%H%M%S')
        print("In function storeface:",self.uniqueID)
        
        #Storing User Details in CSV file
        d = {'ID': [self.uniqueID], 'Name':[self.UName], 'Mail':[self.MailID], 'Mobile':[self.mobileNo],'Organization':[self.org] }
        data = pd.DataFrame(data = d)
        with open('User_Details.csv', 'a') as f:
            data.to_csv(f, header = False)

        userFolder = "./training_images/"+self.uniqueID
        if not os.path.exists(userFolder):
            os.makedirs(userFolder)
            
        if os.path.exists(self.dirname):
            files = os.listdir(self.dirname)
            for f in files:
                shutil.move(self.dirname+"/"+f, userFolder) 
            #shutil.move(self.dirname, userFolder)
            os.rmdir(self.dirname)
            print("Creation, moving and deletion done")
        
    def onClose(self, wasClean, code, reason):
        print("WebSocket connection closed: {0}".format(reason))
        print("Called Close connection")
        if os.path.exists(self.dirname):
            print("Inside the if", self.dirname)
            shutil.move(self.dirname,"./uselessFaces")
            #shutil.remove(self.dirname)
            print("Directory Moved Successful")

    def loadState(self, jsImages, training, jsPeople):
        self.training = training

        for jsImage in jsImages:
            h = jsImage['hash'].encode('ascii', 'ignore')
            self.images[h] = Face(np.array(jsImage['representation']),
                                  jsImage['identity'])

        for jsPerson in jsPeople:
            self.people.append(jsPerson.encode('ascii', 'ignore'))

        if not training:
            self.trainSVM()

    def getData(self):
        X = []
        y = []
        for img in self.images.values():
            X.append(img.rep)
            y.append(img.identity)

        numIdentities = len(set(y + [-1])) - 1
        if numIdentities == 0:
            return None

        if args.unknown:
            numUnknown = y.count(-1)
            numIdentified = len(y) - numUnknown
            numUnknownAdd = (numIdentified / numIdentities) - numUnknown
            if numUnknownAdd > 0:
                print("+ Augmenting with {} unknown images.".format(numUnknownAdd))
                for rep in self.unknownImgs[:numUnknownAdd]:
                    # print(rep)
                    X.append(rep)
                    y.append(-1)

        X = np.vstack(X)
        y = np.array(y)
        return (X, y)

    def sendTSNE(self, people):
        d = self.getData()
        if d is None:
            return
        else:
            (X, y) = d

        X_pca = PCA(n_components=50).fit_transform(X, X)
        tsne = TSNE(n_components=2, init='random', random_state=0)
        X_r = tsne.fit_transform(X_pca)

        yVals = list(np.unique(y))
        colors = cm.rainbow(np.linspace(0, 1, len(yVals)))

        # print(yVals)

        plt.figure()
        for c, i in zip(colors, yVals):
            name = "Unknown" if i == -1 else people[i]
            plt.scatter(X_r[y == i, 0], X_r[y == i, 1], c=c, label=name)
            plt.legend()

        imgdata = StringIO.StringIO()
        plt.savefig(imgdata, format='png')
        imgdata.seek(0)

        content = 'data:image/png;base64,' + \
                  urllib.quote(base64.b64encode(imgdata.buf))
        msg = {
            "type": "TSNE_DATA",
            "content": content
        }
        self.sendMessage(json.dumps(msg))

    def trainSVM(self):
        print("+ Training SVM on {} labeled images.".format(len(self.images)))
        d = self.getData()
        if d is None:
            self.svm = None
            return
        else:
            (X, y) = d
            numIdentities = len(set(y + [-1]))
            if numIdentities <= 1:
                return

            param_grid = [
                {'C': [1, 10, 100, 1000],
                 'kernel': ['linear']},
                {'C': [1, 10, 100, 1000],
                 'gamma': [0.001, 0.0001],
                 'kernel': ['rbf']}
            ]
            self.svm = GridSearchCV(SVC(C=1), param_grid, cv=5).fit(X, y)
            pickle.dump(self.svm, open(model_location, 'wb'))
            print("Saved in the SVM to model.sav file")


    def TrainAllImages(self):
        # Loading Data into self.images
        os.chdir('./training_images')
        for fname in os.listdir("."):
            if os.path.isdir(fname):
                print("Reading images in ", fname)
                self.people.append(int(fname))
                for i in os.listdir(fname):
                    alignedFace = cv2.imread(os.path.join(fname,i))
                    try:
                        img = net.forward(alignedFace)
                    except AssertionError:
                        continue
                    #print(len(img))
                    rep = Face(np.array(img), int(fname))
                    #print(rep)
                    phash = str(imagehash.phash(Image.fromarray(alignedFace)))
                    self.images[phash] = rep
        os.chdir('..')
        self.trainSVM()

    def processFrame(self, dataURL, identity, id):
        
        head = "data:image/jpeg;base64,"
        assert(dataURL.startswith(head))
        imgdata = base64.b64decode(dataURL[len(head):])
        imgF = StringIO.StringIO()
        imgF.write(imgdata)
        imgF.seek(0)
        img = Image.open(imgF)

        buf = np.fliplr(np.asarray(img))
        rgbFrame = np.zeros((300, 400, 3), dtype=np.uint8)
        rgbFrame[:, :, 0] = buf[:, :, 2]
        rgbFrame[:, :, 1] = buf[:, :, 1]
        rgbFrame[:, :, 2] = buf[:, :, 0]

        if not self.training:
            annotatedFrame = np.copy(buf)
        identities = []
        assert rgbFrame is not None
        bbs = align.getAllFaceBoundingBoxes(rgbFrame)
        print(len(bbs))
        if len(bbs) > 1:
            print("More than one person in front of cam")
            msg = {
                 "type": "WARNING",
                 "message": "Please make ensure only one person is infront of the cam"
             }
            self.sendMessage(json.dumps(msg))
            return

        if len(bbs) == 0:
            print("No human face detected")
            msg = {
                 "type": "WARNING",
                 "message": "No face found, please be present in front of the camera, alone!!"
             }
            self.sendMessage(json.dumps(msg))
            return
        bb = align.getLargestFaceBoundingBox(rgbFrame)
        bbs = [bb] if bb is not None else []
        for bb in bbs:
            # print(len(bbs))
            landmarks = align.findLandmarks(rgbFrame, bb)
            alignedFace = align.align(args.imgDim, rgbFrame, bb,
                                      landmarks=landmarks,
                                      landmarkIndices=openface.AlignDlib.OUTER_EYES_AND_NOSE)
            if alignedFace is None:
                continue

            phash = str(imagehash.phash(Image.fromarray(alignedFace)))
            if phash in self.images:
                identity = self.images[phash].identity
            else:

                print("came here")
                print("Unique Id: ",id)
                if(id == 0):
                    tempPath = self.dirname
                    if not os.path.exists(tempPath):
                        os.makedirs(tempPath)         

                    cv2.imwrite(tempPath+"/"+str(self.frameNum)+".jpeg", alignedFace)
                else:
                    tempPath = 'training_images/'+str(id)
                    if not os.path.exists(tempPath):
                        os.makedirs(tempPath) 
                    cv2.imwrite(tempPath+"/"+str(id)+str(self.frameNum)+".jpeg", alignedFace)

    def processFrame_testing(self, dataURL):
        
        head = "data:image/jpeg;base64,"
        assert(dataURL.startswith(head))
        imgdata = base64.b64decode(dataURL[len(head):])
        imgF = StringIO.StringIO()
        imgF.write(imgdata)
        imgF.seek(0)
        img = Image.open(imgF)

        buf = np.fliplr(np.asarray(img))
        rgbFrame = np.zeros((300, 400, 3), dtype=np.uint8)
        rgbFrame[:, :, 0] = buf[:, :, 2]
        rgbFrame[:, :, 1] = buf[:, :, 1]
        rgbFrame[:, :, 2] = buf[:, :, 0]

        if self.testing:
            annotatedFrame = np.copy(buf)

        # cv2.imshow('frame', rgbFrame)
        # if cv2.waitKey(1) & 0xFF == ord('q'):
        #     return

        ####### loading SVM (Load svm)
        if self.svm is None:
            print("Loading SVM model file")
            self.svm = pickle.load(open(model_location, 'rb'))
            print(self.svm)

        #Opening CSV
        if self.details is None:
            self.details = pd.read_csv('User_Details.csv')

        #identities = []
        identity = -1
        # bbs = align.getAllFaceBoundingBoxes(rgbFrame)

        assert rgbFrame is not None
        bbs = align.getAllFaceBoundingBoxes(rgbFrame)
        print(len(bbs))
        if len(bbs) > 1:
            print("More than one person in front of cam")
            msg = {
                 "type": "WARNING",
                 "message": "Please make ensure only one person is infront of the cam"
             }
            self.sendMessage(json.dumps(msg))
            return

        if len(bbs) == 0:
            print("No human face detected")
            msg = {
                 "type": "WARNING",
                 "message": "No face found, please be present in front of the camera, alone!!"
             }
            self.sendMessage(json.dumps(msg))
            return
        
        ##------------------End of Handling no face or more than one face ----------------------------------

        bb = align.getLargestFaceBoundingBox(rgbFrame)
        bbs = [bb] if bb is not None else []
        for bb in bbs:
            # print(len(bbs))
            landmarks = align.findLandmarks(rgbFrame, bb)
            alignedFace = align.align(args.imgDim, rgbFrame, bb,
                                      landmarks=landmarks,
                                      landmarkIndices=openface.AlignDlib.OUTER_EYES_AND_NOSE)
            if alignedFace is None:
                continue

            phash = str(imagehash.phash(Image.fromarray(alignedFace)))
            if phash in self.images:
                identity = self.images[phash].identity
            else:
                rep = net.forward(alignedFace)
                #print(rep)
                #if self.training:
                #    self.images[phash] = Face(rep, identity)
                #    # TODO: Transferring as a string is suboptimal.
                #    content = [str(x) for x in cv2.resize(alignedFace, (0,0),
                #    fx=0.5, fy=0.5).flatten()]
                #    content = [str(x) for x in alignedFace.flatten()]
                #    msg = {
                #        "type": "NEW_IMAGE",
                #        "hash": phash,
                #        "content": content,
                #        "identity": identity,
                #        "representation": rep.tolist()
                #    }
                #    self.sendMessage(json.dumps(msg))
                #else
                if self.testing:
                    #if len(self.people) == 0:
                    #    identity = -1
                    #elif len(self.people) == 1:
                    #    identity = 0
                    if self.svm:
                        print("Came here")
                        identity = self.svm.predict(rep.tolist())[0]
                    else:
                        print("hhh")
                        identity = -1
                    #if identity not in identities:
                    #    identities.append(identity)
                self.prediction = identity
            #if not self.training:
            if self.testing:
                bl = (bb.left(), bb.bottom())
                tr = (bb.right(), bb.top())
                cv2.rectangle(annotatedFrame, bl, tr, color=(153, 255, 204),
                              thickness=3)
                for p in openface.AlignDlib.OUTER_EYES_AND_NOSE:
                    cv2.circle(annotatedFrame, center=landmarks[p], radius=3,
                               color=(102, 204, 255), thickness=-1)
                if identity == -1:
                    if len(self.people) == 1:
                        name = self.people[0]
                    else:
                        name = "Unknown"
                else:
                    #name = self.people[identity]
                    details = self.details[self.details['ID']==identity]
                    #print(details)
                    name  = details['Name'].values[0]
                    print(name)
                cv2.putText(annotatedFrame, name, (bb.left(), bb.top() - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, fontScale=0.75,
                            color=(152, 255, 204), thickness=2)

        # if not self.training:
        if identity!=-1 and self.testing:
            msg = {
                "type": "IDENTITIES",
                "identities": identity,
                "name": details['Name'].values[0],
                "mail": details['Mail'].values[0],
                "company": details['Company'].values[0]
            }
            self.sendMessage(json.dumps(msg))

            plt.figure()
            plt.imshow(annotatedFrame)
            plt.xticks([])
            plt.yticks([])

            imgdata = StringIO.StringIO()
            plt.savefig(imgdata, format='png')
            imgdata.seek(0)
            content = 'data:image/png;base64,' + \
                urllib.quote(base64.b64encode(imgdata.buf))
            msg = {
                "type": "ANNOTATED",
                "content": content
            }
            plt.close()
            self.sendMessage(json.dumps(msg))
    def processFeedback(self,value, actualMail):
        print("SYYYYYYYYYYYYYYYYYYYYYY")
        predictedMail = self.details[self.details['ID'] == self.prediction]['Mail'].values[0]
        if value == True:
            d = {'Result': [value], 'ActualMail':[actualMail], 'PredictedMail':[actualMail]}
        else:
            d = {'Result': [value], 'ActualMail':[actualMail], 'PredictedMail':[predictedMail]}
        data = pd.DataFrame(data = d)
        with open('results.csv', 'a') as f:
            data.to_csv(f, header = False)
        print("feedback taken")

def main(reactor):
    log.startLogging(sys.stdout)
    factory = WebSocketServerFactory()
    factory.protocol = OpenFaceServerProtocol
    ctx_factory = DefaultOpenSSLContextFactory(tls_key, tls_crt)
    reactor.listenSSL(args.port, factory, ctx_factory)
    return defer.Deferred()

if __name__ == '__main__':
    task.react(main)
