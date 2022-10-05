FROM nanome/plugin-env

ENV ARGS=''
WORKDIR /app

ARG CACHEBUST

RUN conda install -c conda-forge cctbx-base

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD python run.py ${ARGS}
