#!/bin/bash
# This scripts downloads the ptb data and unzips it.

DIR="$( cd "$(dirname "$0")" ; pwd -P )"
cd $DIR

echo "Downloading..."

mkdir -p data && cd data
curl https://doc-00-1g-docs.googleusercontent.com/docs/securesc/bi6pep32i46qp6jf4t8ot4enuinqtv0t/9piag4ko9gdq0vo2fv7me2j7pdb3cv9e/1514433600000/13338572596517262068/13338572596517262068/1mj3aVgL73vAoa57MVaBwGx37Qm559XXC?e=download&nonce=sc5n5gemkq12a&user=13338572596517262068&hash=hd5r2p1htqufgbiuljh5j40ig9hv4676 -o inception_v1.ckpt
curl https://doc-04-1g-docs.googleusercontent.com/docs/securesc/bi6pep32i46qp6jf4t8ot4enuinqtv0t/4mu5li9nli83k5blkj4jmnoconk5hedh/1514433600000/13338572596517262068/13338572596517262068/1fu8T2SaICDft752dRY7SoTcmxmyzZx3S?e=download -o resnet_v1_101_2016_08_28.tar.gz
mkdir -p overfeat_rezoom && cd overfeat_rezoom
cd ..
echo "Extracting..."
tar xf resnet_v1_101_2016_08_28.tar.gz

if [[ "$1" == '--travis_tiny_data' ]]; then
    curl https://doc-04-1g-docs.googleusercontent.com/docs/securesc/bi6pep32i46qp6jf4t8ot4enuinqtv0t/jd8ofesjibp01uc9f5pc2i56c4toak3a/1514433600000/13338572596517262068/13338572596517262068/1B-LDfk3hh_SKTydptjxdvQHylN8EpiDN?e=download -o brainwash_tiny.tar.gz
    tar xf brainwash_tiny.tar.gz
    echo "Done."
else
    curl https://doc-10-1g-docs.googleusercontent.com/docs/securesc/bi6pep32i46qp6jf4t8ot4enuinqtv0t/6k2kc1jksu0bgcvbd0qkujkvs84i0gj5/1514433600000/13338572596517262068/13338572596517262068/1CT4lLdVVlDlAgx81jh8cUn3R0nX68eap?e=download -o save.ckpt-150000v2
    curl https://doc-0k-6g-docs.googleusercontent.com/docs/securesc/bi6pep32i46qp6jf4t8ot4enuinqtv0t/42bmdbh0lkslbi14kpf8n7aor3d9f8u4/1514433600000/01108849748894963768/13338572596517262068/0B745B1U5fg09RjZrQ1gzOTJVdkk?e=download -o brainwash.tar.gz
    tar xf brainwash.tar.gz
    echo "Done."
fi
