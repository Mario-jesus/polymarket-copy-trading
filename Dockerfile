FROM python:3.13.5-alpine3.22
RUN apk add --no-cache gcc g++ python3-dev musl-dev linux-headers nano
RUN mkdir -p /app
WORKDIR /app/
RUN pip install pipenv
COPY Pipfile .
RUN pipenv install --clear
COPY . .
RUN mkdir -p /root/.jupyter
RUN echo "c.NotebookApp.token = ''" > /root/.jupyter/jupyter_notebook_config.py
RUN echo "c.NotebookApp.password = ''" >> /root/.jupyter/jupyter_notebook_config.py
EXPOSE 8888
CMD ["pipenv", "run", "python", "-m", "jupyter", "notebook", "--ip=0.0.0.0", "--no-browser", "--allow-root"]
