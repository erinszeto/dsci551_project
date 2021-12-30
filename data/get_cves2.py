import requests
import pandas as pd
import time
from datetime import datetime
import pickle
import sys

def get_inputs():
    inputs = sys.argv[1:]
    startIndex = int(inputs[0])
    fileName = inputs[1]
    return startIndex,fileName

def get_CVEs(url,index):
    r = requests.get(url)
    try:
        response = r.json()

        total_results = response["totalResults"]
    #   cve_data_timestamp = response["result"]["CVE_data_timestamp"][:-1]
        cves = response["result"]["CVE_Items"] #list of CVE dictionaries/JSON
        return total_results,cves

    except ValueError:
        print(r.text)
        # pickle.dump(r, open("{0}.pkl".format(index),"wb"))
        # print("Response content is not valid JSON")
        return False,False


def get_URL(index):
    url = "https://services.nvd.nist.gov/rest/json/cves/1.0?startIndex={0}&pubStartDate=2019-01-01T00:00:00:000%20UTC-00:00&resultsPerPage=2000".format(str(index))
    return url

def get_CVEinfo(cve):
    cve_id = cve["cve"]["CVE_data_meta"]["ID"]
    description = cve["cve"]["description"]["description_data"][0]["value"]
    references=';'.join([x["url"] for x in cve["cve"]["references"]["reference_data"]])
    publishedDate=cve["publishedDate"]
    lastModifiedDate=cve['lastModifiedDate']
    
    if "impact" not in cve:
        dic = {"id":cve_id, "description":description,"references":references,"publishedDate":publishedDate,"lastModifiedDate":lastModifiedDate}
        return dic
    else:
        try:
            baseScore=cve["impact"]["baseMetricV3"]["cvssV3"]["baseScore"]
            baseSeverity=cve["impact"]["baseMetricV3"]["cvssV3"]["baseSeverity"]
            attackVector=cve["impact"]["baseMetricV3"]["cvssV3"]["attackVector"]
            attackComplexity=cve["impact"]["baseMetricV3"]["cvssV3"]["attackComplexity"]
            
            dic = {"id":cve_id,"description":description,"references":references,"publishedDate":publishedDate,"lastModifiedDate":lastModifiedDate,\
                "attackVector":attackVector,"attackComplexity":attackComplexity,"baseScore":baseScore,"baseSeverity":baseSeverity}
            return dic
        
        except KeyError:
            print(cve["impact"])
            dic = {"id":cve_id, "description":description,"references":references,"publishedDate":publishedDate,"lastModifiedDate":lastModifiedDate}
            return dic

def get_data(startIndex):
    index = startIndex
    url = get_URL(index)
    cve_dics = []

    total_results, cves = get_CVEs(url,index)
    if cves == False:
        print("504 Gateway Timeout")
        return "no data"

    print(total_results)
    print("First 2000 Done")
    cve_dics = cve_dics + [get_CVEinfo(cve) for cve in cves]

    index += 2000
    while (index < total_results):
        time.sleep(60)
        print("Starting at %s index" % str(index))
        url = get_URL(index)
        total, cves = get_CVEs(url,index)
        if cves == False:
            print("Stopped at {0} index".format(index))
            return cve_dics
        cve_dics = cve_dics + [get_CVEinfo(cve) for cve in cves]

        index += 2000

    return cve_dics

def export_CSV(dics,fileName):
    df = pd.DataFrame(dics)
    df.to_csv(fileName,index=False)
    return

def main():
    startIndex,fileName = get_inputs()
    cve_dics = get_data(startIndex)
    if cve_dics == "no data":
        return
    export_CSV(cve_dics,fileName)

if __name__ == '__main__':
    main()