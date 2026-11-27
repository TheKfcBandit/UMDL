"""Post pages as Reddit serves them to a browser, cut down to what matters.

The post is one <shreddit-post> element. Its attributes say what kind of post
it is; its media is in the elements inside. These follow Reddit's markup as of
late 2026; Reddit itself cannot be reached from where the tests run.
"""

HEAD = ('<html><head><title>{title} : r/me_irl</title></head><body><shreddit-app>'
        '<faceplate-tracker><img src="https://styles.redditmedia.com/t5_2vegg/styles/communityIcon_x.png"></faceplate-tracker>')
TAIL = ('<shreddit-comment-tree><shreddit-comment author="someone">'
        '<img src="https://preview.redd.it/a-reply-v0-notthepost.jpg?width=320&amp;s=1"></shreddit-comment>'
        '</shreddit-comment-tree></shreddit-app></body></html>')


def post(kind, href, inside, title="Holiday photos", ident="1abcde"):
    return (HEAD.format(title=title) +
            '<shreddit-post class="block" permalink="/r/me_irl/comments/{id}/a_post/" '
            'content-href="{href}" comment-count="12" post-title="{title}" post-type="{kind}" '
            'score="321" id="t3_{id}" author="someone" subreddit-prefixed-name="r/me_irl">'
            '<img slot="credit-bar" src="https://i.redd.it/snoovatar/avatars/1234-headshot.png">'
            '{inside}</shreddit-post>'.format(id=ident, href=href, title=title, kind=kind, inside=inside) + TAIL)


def gallery(count, title="Holiday photos"):
    def slide(index):
        name = "holiday-photos-v0-img%02d.jpg" % index
        source = "https://preview.redd.it/%s?width=1080&amp;crop=smart&amp;auto=webp&amp;s=abc%d" % (name, index)
        if index == 0:
            return ('<li><figure><img class="media-lightbox-img" src="%s" srcset="%s 640w, %s 1080w">'
                    '</figure></li>' % (source, source.replace("1080", "640"), source))
        return '<li><figure><img class="media-lightbox-img" data-lazy-src="%s"></figure></li>' % source
    return post("gallery", "https://www.reddit.com/gallery/1abcde",
                "<gallery-carousel><ul>%s</ul></gallery-carousel>" % "".join(slide(i) for i in range(count)),
                title)


IMAGE = post("image", "https://i.redd.it/qyvi7xrehmwh1.jpeg",
             '<shreddit-aspect-ratio><img class="media-lightbox-img" alt="r/me_irl - A picture" '
             'src="https://preview.redd.it/a-picture-v0-qyvi7xrehmwh1.jpeg?auto=webp&amp;s=77"></shreddit-aspect-ratio>',
             "A picture")

VIDEO = post("video", "https://v.redd.it/abc123",
             '<shreddit-player-2 src="https://v.redd.it/abc123/HLSPlaylist.m3u8?a=1&amp;v=1&amp;f=sd" '
             'preview="https://v.redd.it/abc123/CMAF_96.mp4" '
             'poster="https://external-preview.redd.it/thumb.png?format=pjpg&amp;auto=webp&amp;s=1">'
             '</shreddit-player-2>', "Cat falls off shelf")

LINK = post("link", "https://clips.test/watch/9",
            '<a href="https://clips.test/watch/9"><img src="https://external-preview.redd.it/t.jpg?s=2"></a>',
            "Great clip")

TEXT = post("text", "https://www.reddit.com/r/me_irl/comments/1abcde/a_question/",
            '<div slot="text-body"><p>Does anyone know?</p></div>', "A question")

AWKWARD = post("image", "https://i.redd.it/pic.jpg", "", "Caf&eacute; &amp; &quot;bar&quot; – café \U0001f600")
