# Copyright 2015 Google Inc.
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

"""Client for interacting with the Google Cloud Storage API."""


from google.cloud._helpers import _LocalStack
from google.cloud.client import JSONClient
from google.cloud.exceptions import NotFound
from google.cloud.iterator import HTTPIterator
from google.cloud.storage._http import Connection
from google.cloud.storage.batch import Batch
from google.cloud.storage.bucket import Bucket


class Client(JSONClient):
    """Client to bundle configuration needed for API requests.

    :type project: str
    :param project: the project which the client acts on behalf of. Will be
                    passed when creating a topic.  If not passed,
                    falls back to the default inferred from the environment.

    :type credentials: :class:`oauth2client.client.OAuth2Credentials` or
                       :class:`NoneType`
    :param credentials: The OAuth2 Credentials to use for the connection
                        owned by this client. If not passed (and if no ``http``
                        object is passed), falls back to the default inferred
                        from the environment.

    :type http: :class:`httplib2.Http` or class that defines ``request()``.
    :param http: An optional HTTP object to make requests. If not passed, an
                 ``http`` object is created that is bound to the
                 ``credentials`` for the current object.
    """

    _connection_class = Connection

    def __init__(self, project=None, credentials=None, http=None):
        self._base_connection = None
        super(Client, self).__init__(project=project, credentials=credentials,
                                     http=http)
        self._batch_stack = _LocalStack()

    @property
    def _connection(self):
        """Get connection or batch on the client.

        :rtype: :class:`google.cloud.storage._http.Connection`
        :returns: The connection set on the client, or the batch
                  if one is set.
        """
        if self.current_batch is not None:
            return self.current_batch
        else:
            return self._base_connection

    @_connection.setter
    def _connection(self, value):
        """Set connection on the client.

        Intended to be used by constructor (since the base class calls)
            self._connection = connection
        Will raise if the connection is set more than once.

        :type value: :class:`google.cloud.storage._http.Connection`
        :param value: The connection set on the client.

        :raises: :class:`ValueError` if connection has already been set.
        """
        if self._base_connection is not None:
            raise ValueError('Connection already set on client')
        self._base_connection = value

    def _push_batch(self, batch):
        """Push a batch onto our stack.

        "Protected", intended for use by batch context mgrs.

        :type batch: :class:`google.cloud.storage.batch.Batch`
        :param batch: newly-active batch
        """
        self._batch_stack.push(batch)

    def _pop_batch(self):
        """Pop a batch from our stack.

        "Protected", intended for use by batch context mgrs.

        :raises: IndexError if the stack is empty.
        :rtype: :class:`google.cloud.storage.batch.Batch`
        :returns: the top-most batch/transaction, after removing it.
        """
        return self._batch_stack.pop()

    @property
    def current_batch(self):
        """Currently-active batch.

        :rtype: :class:`google.cloud.storage.batch.Batch` or ``NoneType`` (if
                no batch is active).
        :returns: The batch at the top of the batch stack.
        """
        return self._batch_stack.top

    def bucket(self, bucket_name):
        """Factory constructor for bucket object.

        .. note::
          This will not make an HTTP request; it simply instantiates
          a bucket object owned by this client.

        :type bucket_name: str
        :param bucket_name: The name of the bucket to be instantiated.

        :rtype: :class:`google.cloud.storage.bucket.Bucket`
        :returns: The bucket object created.
        """
        return Bucket(client=self, name=bucket_name)

    def batch(self):
        """Factory constructor for batch object.

        .. note::
          This will not make an HTTP request; it simply instantiates
          a batch object owned by this client.

        :rtype: :class:`google.cloud.storage.batch.Batch`
        :returns: The batch object created.
        """
        return Batch(client=self)

    def get_bucket(self, bucket_name):
        """Get a bucket by name.

        If the bucket isn't found, this will raise a
        :class:`google.cloud.storage.exceptions.NotFound`.

        For example:

        .. code-block:: python

          >>> try:
          >>>   bucket = client.get_bucket('my-bucket')
          >>> except google.cloud.exceptions.NotFound:
          >>>   print('Sorry, that bucket does not exist!')

        This implements "storage.buckets.get".

        :type bucket_name: str
        :param bucket_name: The name of the bucket to get.

        :rtype: :class:`google.cloud.storage.bucket.Bucket`
        :returns: The bucket matching the name provided.
        :raises: :class:`google.cloud.exceptions.NotFound`
        """
        bucket = Bucket(self, name=bucket_name)
        bucket.reload(client=self)
        return bucket

    def lookup_bucket(self, bucket_name):
        """Get a bucket by name, returning None if not found.

        You can use this if you would rather check for a None value
        than catching an exception:

        .. code-block:: python

          >>> bucket = client.lookup_bucket('doesnt-exist')
          >>> print(bucket)
          None
          >>> bucket = client.lookup_bucket('my-bucket')
          >>> print(bucket)
          <Bucket: my-bucket>

        :type bucket_name: str
        :param bucket_name: The name of the bucket to get.

        :rtype: :class:`google.cloud.storage.bucket.Bucket`
        :returns: The bucket matching the name provided or None if not found.
        """
        try:
            return self.get_bucket(bucket_name)
        except NotFound:
            return None

    def create_bucket(self, bucket_name):
        """Create a new bucket.

        For example:

        .. code-block:: python

          >>> bucket = client.create_bucket('my-bucket')
          >>> print(bucket)
          <Bucket: my-bucket>

        This implements "storage.buckets.insert".

        If the bucket already exists, will raise
        :class:`google.cloud.exceptions.Conflict`.

        :type bucket_name: str
        :param bucket_name: The bucket name to create.

        :rtype: :class:`google.cloud.storage.bucket.Bucket`
        :returns: The newly created bucket.
        """
        bucket = Bucket(self, name=bucket_name)
        bucket.create(client=self)
        return bucket

    def list_buckets(self, max_results=None, page_token=None, prefix=None,
                     projection='noAcl', fields=None):
        """Get all buckets in the project associated to the client.

        This will not populate the list of blobs available in each
        bucket.

        .. code-block:: python

          >>> for bucket in client.list_buckets():
          ...   print(bucket)

        This implements "storage.buckets.list".

        :type max_results: int
        :param max_results: Optional. Maximum number of buckets to return.

        :type page_token: str
        :param page_token: Optional. Opaque marker for the next "page" of
                           buckets. If not passed, will return the first page
                           of buckets.

        :type prefix: str
        :param prefix: Optional. Filter results to buckets whose names begin
                       with this prefix.

        :type projection: str
        :param projection:
            (Optional) Specifies the set of properties to return. If used, must
            be 'full' or 'noAcl'. Defaults to 'noAcl'.

        :type fields: str
        :param fields:
            (Optional) Selector specifying which fields to include in a partial
            response. Must be a list of fields. For example to get a partial
            response with just the next page token and the language of each
            bucket returned: 'items/id,nextPageToken'

        :rtype: :class:`~google.cloud.iterator.Iterator`
        :returns: Iterator of all :class:`~google.cloud.storage.bucket.Bucket`
                  belonging to this project.
        """
        extra_params = {'project': self.project}

        if prefix is not None:
            extra_params['prefix'] = prefix

        extra_params['projection'] = projection

        if fields is not None:
            extra_params['fields'] = fields

        return HTTPIterator(
            client=self, path='/b', item_to_value=_item_to_bucket,
            page_token=page_token, max_results=max_results,
            extra_params=extra_params)


def _item_to_bucket(iterator, item):
    """Convert a JSON bucket to the native object.

    :type iterator: :class:`~google.cloud.iterator.Iterator`
    :param iterator: The iterator that has retrieved the item.

    :type item: dict
    :param item: An item to be converted to a bucket.

    :rtype: :class:`.Bucket`
    :returns: The next bucket in the page.
    """
    name = item.get('name')
    bucket = Bucket(iterator.client, name)
    bucket._set_properties(item)
    return bucket
