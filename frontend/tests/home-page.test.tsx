import { render, screen } from '@testing-library/react'
import Home from '@/app/page'

describe('home page', () => {
  it('defaults to Chinese copy', () => {
    render(<Home />)
    expect(screen.getByText('智能衣橱管理与穿搭推荐')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '立即开始' })).toBeInTheDocument()
  })
})
