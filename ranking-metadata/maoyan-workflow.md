https://www.maoyan.com/board/4

首页：https://www.maoyan.com/board/4
第2页：https://www.maoyan.com/board/4?offset=10
第3页：https://www.maoyan.com/board/4?offset=20

工作流：1.爬取首页的相关内容 2.切换到下一页的url 3.爬取该页的相关内容
重复2-3，直到爬完10页(100条)

内容格式示范：

```html
<div class="content">
  <div class="wrapper">
    <div class="main">
      <p class="update-time">
        2026-04-14<span class="has-fresh-text">已更新</span>
      </p>
      <p class="board-content">
        榜单规则：将猫眼电影库中的经典影片，按照评分和评分人数从高到低综合排序取前100名，每天上午10点更新。相关数据来源于“猫眼电影库”。
      </p>
      <dl class="board-wrapper">
        <dd>
          <i class="board-index board-index-11">11</i>
          <a
            href="/films/46818"
            title="怦然心动"
            class="image-link"
            data-act="boarditem-click"
            data-val="{movieId:46818}"
          >
            <img
              src="//s3.meituan.net/static-prod01/com.sankuai.movie.fe.mywww-files/image/loading_2.e3d934bf.png"
              alt=""
              class="poster-default"
            />
            <img
              data-src="https://p0.pipi.cn/mmdb/d2dad592b122ff8d3387a93ccab6036f616c1.jpg?imageView2/1/w/160/h/220"
              alt="怦然心动"
              class="board-img"
            />
          </a>
          <div class="board-item-main">
            <div class="board-item-content">
              <div class="movie-item-info">
                <p class="name">
                  <a
                    href="/films/46818"
                    title="怦然心动"
                    data-act="boarditem-click"
                    data-val="{movieId:46818}"
                    >怦然心动</a
                  >
                </p>
                <p class="star">
                  主演：玛德琳·卡罗尔,卡兰·麦克奥利菲,艾丹·奎因
                </p>
                <p class="releasetime">上映时间：2010-07-26(美国)</p>
              </div>
              <div class="movie-item-number score-num">
                <p class="score">
                  <i class="integer">8.</i><i class="fraction">9</i>
                </p>
              </div>
            </div>
          </div>
        </dd>
        <dd>
          <i class="board-index board-index-12">12</i>
          <a
            href="/films/1216365"
            title="小偷家族"
            class="image-link"
            data-act="boarditem-click"
            data-val="{movieId:1216365}"
          >
            <img
              src="//s3.meituan.net/static-prod01/com.sankuai.movie.fe.mywww-files/image/loading_2.e3d934bf.png"
              alt=""
              class="poster-default"
            />
            <img
              data-src="https://p0.pipi.cn/mmdb/d2dad5925372ffd7c387a9d01bddad81625c3.jpg?imageView2/1/w/160/h/220"
              alt="小偷家族"
              class="board-img"
            />
          </a>
          <div class="board-item-main">
            <div class="board-item-content">
              <div class="movie-item-info">
                <p class="name">
                  <a
                    href="/films/1216365"
                    title="小偷家族"
                    data-act="boarditem-click"
                    data-val="{movieId:1216365}"
                    >小偷家族</a
                  >
                </p>
                <p class="star">主演：中川雅也,安藤樱,松冈茉优</p>
                ...
              </div>
            </div>
          </div>
        </dd>
      </dl>
    </div>
  </div>
</div>
```
